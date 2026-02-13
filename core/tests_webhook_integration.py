"""
Integration tests for the Stripe webhook endpoint.
Tests the full flow: HTTP request -> signature verification -> store -> enqueue -> response.

Under the new architecture, the view ALWAYS returns 200 for valid signed events
(acknowledge fast). Processing happens in Celery. The tests verify storage and
enqueue behavior, not handler execution.
"""
import json
import time
import hmac
import hashlib
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import WebhookEvent
from testing_utils import make_customer, make_stripe_subscription_data


WEBHOOK_SECRET = "whsec_test_secret"


def _make_stripe_signature(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Generate a valid Stripe webhook signature for testing."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


@override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class WebhookEndpointIntegrationTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/webhooks/stripe/"

    def test_rejects_missing_signature(self):
        response = self.client.post(self.url, data=b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing", response.data["error"])

    def test_rejects_invalid_signature(self):
        response = self.client.post(
            self.url,
            data=b'{"type": "test"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=invalidsig",
        )
        self.assertEqual(response.status_code, 400)

    @patch("core.tasks.process_webhook_event.delay")
    @patch("core.views.stripe.Webhook.construct_event")
    def test_returns_200_and_enqueues_task(self, mock_construct, mock_delay):
        make_customer(stripe_customer_id="cus_int_test")
        sub_data = make_stripe_subscription_data(
            sub_id="sub_int_test",
            customer_id="cus_int_test",
            price_id="price_pro_monthly",
            status="active",
        )

        mock_event = MagicMock()
        mock_event.id = "evt_success"
        mock_event.type = "customer.subscription.created"
        mock_event.data.object = sub_data
        mock_construct.return_value = mock_event

        response = self.client.post(
            self.url,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=test",
        )

        self.assertEqual(response.status_code, 200)

        # Event stored with payload
        event = WebhookEvent.objects.get(stripe_event_id="evt_success")
        self.assertEqual(event.event_type, "customer.subscription.created")
        self.assertEqual(event.payload, sub_data)
        self.assertFalse(event.processed)

        # Celery task enqueued
        mock_delay.assert_called_once_with("evt_success")

    @patch("core.tasks.process_webhook_event.delay")
    @patch("core.views.stripe.Webhook.construct_event")
    def test_returns_200_for_duplicate_event(self, mock_construct, mock_delay):
        WebhookEvent.objects.create(
            stripe_event_id="evt_dup",
            event_type="test",
            payload={},
        )

        mock_event = MagicMock()
        mock_event.id = "evt_dup"
        mock_event.type = "test"
        mock_construct.return_value = mock_event

        response = self.client.post(
            self.url,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=test",
        )

        self.assertEqual(response.status_code, 200)
        # Should NOT enqueue for duplicate
        mock_delay.assert_not_called()

    @patch("core.tasks.process_webhook_event.delay")
    @patch("core.views.stripe.Webhook.construct_event")
    def test_stores_payload_for_later_processing(self, mock_construct, mock_delay):
        """
        The key architectural change: the view stores the event payload
        and returns 200 immediately. Stripe never sees a 500.
        """
        mock_event = MagicMock()
        mock_event.id = "evt_payload_test"
        mock_event.type = "invoice.paid"
        mock_event.data.object = {"id": "in_123", "customer": "cus_123", "amount": 2999}
        mock_construct.return_value = mock_event

        response = self.client.post(
            self.url,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=test",
        )

        self.assertEqual(response.status_code, 200)

        event = WebhookEvent.objects.get(stripe_event_id="evt_payload_test")
        self.assertEqual(event.payload["id"], "in_123")
        self.assertEqual(event.payload["amount"], 2999)
        self.assertFalse(event.processed)


@override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class ProcessWebhookEventTaskTest(TestCase):
    """Tests the Celery task that processes stored events."""

    def test_processes_event_and_marks_done(self):
        from core.tasks import process_webhook_event

        make_customer(stripe_customer_id="cus_task_test")
        sub_data = make_stripe_subscription_data(
            sub_id="sub_task_test",
            customer_id="cus_task_test",
            price_id="price_pro_monthly",
            status="active",
        )

        event = WebhookEvent.objects.create(
            stripe_event_id="evt_task_test",
            event_type="customer.subscription.created",
            payload=sub_data,
        )

        process_webhook_event("evt_task_test")

        event.refresh_from_db()
        self.assertTrue(event.processed)
        self.assertIsNotNone(event.processed_at)

    def test_marks_event_done_on_webhook_skip(self):
        """WebhookSkip is expected — event should be marked processed."""
        from core.tasks import process_webhook_event

        event = WebhookEvent.objects.create(
            stripe_event_id="evt_skip_task",
            event_type="customer.subscription.updated",
            payload=make_stripe_subscription_data(sub_id="sub_nonexistent"),
        )

        process_webhook_event("evt_skip_task")

        event.refresh_from_db()
        self.assertTrue(event.processed)

    def test_skips_already_processed(self):
        from core.tasks import process_webhook_event
        from django.utils import timezone

        event = WebhookEvent.objects.create(
            stripe_event_id="evt_already_done",
            event_type="test",
            payload={},
            processed=True,
            processed_at=timezone.now(),
        )

        # Should not raise or re-dispatch
        process_webhook_event("evt_already_done")

    def test_retries_on_exception(self):
        """Transient failures trigger Celery retry."""
        from core.tasks import process_webhook_event
        from core.stripe.event_handler import WebhookHandler

        event = WebhookEvent.objects.create(
            stripe_event_id="evt_retry_task",
            event_type="test.retry.event",
            payload={},
        )

        class _RetryHandler(WebhookHandler):
            __event__ = "test.retry.event"
            __atomic__ = False

            @classmethod
            def handle(cls, data: dict):
                raise RuntimeError("transient failure")

        with self.assertRaises(RuntimeError):
            # In test mode, Celery runs synchronously and the retry raises
            process_webhook_event("evt_retry_task")

        event.refresh_from_db()
        self.assertFalse(event.processed)

        WebhookHandler.__handlers__["test.retry.event"].remove(_RetryHandler)
