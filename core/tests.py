from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

from core.models import WebhookEvent, WebhookHandlerResult, ScheduledEvent, EventType
from core.stripe import WebhookHandler, dispatch_event
from core.stripe.models import StripeSubscription, StripeInvoice, StripeCharge, _ensure_datetime
from core.views import health_check


class TimestampConversionTest(TestCase):

    def test_returns_aware_utc_datetime(self):
        from datetime import timezone as dt_timezone
        ts = 1700000000
        result = _ensure_datetime(ts)
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.tzinfo, dt_timezone.utc)

    def test_subscription_optional_fields_default_to_none(self):
        data = {
            "id": "sub_test",
            "customer": "cus_test",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_123"}}]},
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "cancel_at_period_end": False,
        }
        sub = StripeSubscription.model_validate(data)

        self.assertIsNotNone(sub.current_period_start_dt.tzinfo)
        self.assertIsNotNone(sub.current_period_end_dt.tzinfo)
        self.assertIsNone(sub.canceled_at_dt)
        self.assertIsNone(sub.trial_start_dt)


class StripeInvoiceModelTest(TestCase):

    def test_line_amount_converts_cents_to_dollars(self):
        inv = StripeInvoice.model_validate({
            "id": "in_test",
            "customer": "cus_test",
            "billing_reason": "subscription_create",
            "lines": {
                "data": [
                    {"amount": 2999, "description": "Pro Monthly", "price": {"id": "price_pro"}}
                ]
            },
        })
        self.assertEqual(inv.lines.data[0].amount_dollars, Decimal("29.99"))
        self.assertEqual(inv.lines.data[0].price_id, "price_pro")


class StripeChargeModelTest(TestCase):

    def test_refund_amount_converts_cents_to_dollars(self):
        charge = StripeCharge.model_validate({
            "id": "ch_test",
            "invoice": "in_test",
            "amount_refunded": 1500,
        })
        self.assertEqual(charge.amount_refunded_dollars, Decimal("15.00"))


class WebhookHandlerRegistryTest(TestCase):
    """
    Tests __init_subclass__ auto-registration.
    Defines a temporary handler class, verifies it appears in the registry,
    then cleans up.
    """

    def test_subclass_registers_automatically(self):
        class _TestAutoHandler(WebhookHandler):
            __event__ = "test.auto.register"

            @classmethod
            def handle(cls, data: dict):
                pass

        handlers = WebhookHandler.handlers_for("test.auto.register")
        self.assertIn(_TestAutoHandler, handlers)

        WebhookHandler.__handlers__["test.auto.register"].remove(_TestAutoHandler)

    def test_dispatch_calls_handler(self):
        call_log = []

        class _TestDispatchHandler(WebhookHandler):
            __event__ = "test.dispatch.event"
            __atomic__ = False

            @classmethod
            def handle(cls, data: dict):
                call_log.append(data)

        count = dispatch_event("test.dispatch.event", {"key": "value"})
        self.assertEqual(count, 1)
        self.assertEqual(call_log, [{"key": "value"}])

        WebhookHandler.__handlers__["test.dispatch.event"].remove(_TestDispatchHandler)

    def test_dispatch_unknown_event_returns_zero(self):
        count = dispatch_event("unknown.event.type.xyz", {})
        self.assertEqual(count, 0)

    def test_multiple_handlers_per_event(self):
        calls = []

        class _TestMultiA(WebhookHandler):
            __event__ = "test.multi.event"
            __atomic__ = False

            @classmethod
            def handle(cls, data: dict):
                calls.append("A")

        class _TestMultiB(WebhookHandler):
            __event__ = "test.multi.event"
            __atomic__ = False

            @classmethod
            def handle(cls, data: dict):
                calls.append("B")

        count = dispatch_event("test.multi.event", {})
        self.assertEqual(count, 2)
        self.assertEqual(calls, ["A", "B"])

        WebhookHandler.__handlers__["test.multi.event"].remove(_TestMultiA)
        WebhookHandler.__handlers__["test.multi.event"].remove(_TestMultiB)


class TrackedDispatchTest(TestCase):
    """Tests per-handler delivery tracking (WebhookHandlerResult)."""

    def test_creates_result_per_handler(self):
        calls = []

        class _TrackedA(WebhookHandler):
            __event__ = "test.tracked"
            __atomic__ = False

            @classmethod
            def handle(cls, data: dict):
                calls.append("A")

        class _TrackedB(WebhookHandler):
            __event__ = "test.tracked"
            __atomic__ = False

            @classmethod
            def handle(cls, data: dict):
                calls.append("B")

        event = WebhookEvent.objects.create(
            stripe_event_id="evt_tracked_test",
            event_type="test.tracked",
            payload={},
        )

        WebhookHandler.dispatch_tracked(event, "test.tracked", {})

        self.assertEqual(calls, ["A", "B"])

        results = WebhookHandlerResult.objects.filter(event=event)
        self.assertEqual(results.count(), 2)
        self.assertTrue(all(r.processed for r in results))

        WebhookHandler.__handlers__["test.tracked"].remove(_TrackedA)
        WebhookHandler.__handlers__["test.tracked"].remove(_TrackedB)

    def test_skips_already_processed_handler(self):
        calls = []

        class _TrackedSkip(WebhookHandler):
            __event__ = "test.tracked.skip"
            __atomic__ = False

            @classmethod
            def handle(cls, data: dict):
                calls.append("called")

        event = WebhookEvent.objects.create(
            stripe_event_id="evt_tracked_skip",
            event_type="test.tracked.skip",
            payload={},
        )

        WebhookHandlerResult.objects.create(
            event=event,
            handler_name=_TrackedSkip.__qualname__,
            processed=True,
            processed_at=timezone.now(),
        )

        WebhookHandler.dispatch_tracked(event, "test.tracked.skip", {})

        self.assertEqual(calls, [])

        WebhookHandler.__handlers__["test.tracked.skip"].remove(_TrackedSkip)


class HealthCheckViewTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    @patch("core.views._check_database", return_value=None)
    @patch("core.views._check_redis", return_value=None)
    @patch("core.views._check_celery", return_value=None)
    @patch("core.views._check_stripe", return_value=None)
    def test_all_healthy(self, *mocks):
        request = self.factory.get("/api/health/")
        response = health_check(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "healthy")

    @patch("core.views._check_database", return_value=None)
    @patch("core.views._check_redis", return_value="connection refused")
    @patch("core.views._check_celery", return_value=None)
    @patch("core.views._check_stripe", return_value=None)
    def test_service_down(self, *mocks):
        request = self.factory.get("/api/health/")
        response = health_check(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "down")
        self.assertEqual(response.data["service_details"]["redis"], "connection refused")


class StripeWebhookViewTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def test_missing_signature_returns_400(self):
        from core.views import stripe_webhook

        request = self.factory.post(
            "/api/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
        )
        request.META.pop("HTTP_STRIPE_SIGNATURE", None)
        response = stripe_webhook(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Missing Stripe-Signature header")

    @patch("core.tasks.process_webhook_event.delay")
    @patch("core.views.stripe.Webhook.construct_event")
    def test_duplicate_event_returns_200(self, mock_construct, mock_delay):
        from core.views import stripe_webhook

        mock_event = MagicMock()
        mock_event.id = "evt_duplicate"
        mock_event.type = "invoice.paid"
        mock_event.data.object = {}
        mock_construct.return_value = mock_event

        WebhookEvent.objects.create(
            stripe_event_id="evt_duplicate",
            event_type="invoice.paid",
            payload={},
        )

        request = self.factory.post(
            "/api/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_sig",
        )
        response = stripe_webhook(request)
        self.assertEqual(response.status_code, 200)
        mock_delay.assert_not_called()

    @patch("core.tasks.process_webhook_event.delay")
    @patch("core.views.stripe.Webhook.construct_event")
    def test_valid_event_stores_and_enqueues(self, mock_construct, mock_delay):
        from core.views import stripe_webhook

        mock_event = MagicMock()
        mock_event.id = "evt_new"
        mock_event.type = "customer.subscription.created"
        mock_event.data.object = {"id": "sub_123"}
        mock_construct.return_value = mock_event

        request = self.factory.post(
            "/api/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_sig",
        )
        response = stripe_webhook(request)
        self.assertEqual(response.status_code, 200)

        event = WebhookEvent.objects.get(stripe_event_id="evt_new")
        self.assertEqual(event.payload, {"id": "sub_123"})
        self.assertFalse(event.processed)

        mock_delay.assert_called_once_with("evt_new")


class CleanupWebhookEventsTest(TestCase):

    def test_deletes_old_events_only(self):
        from core.tasks import cleanup_webhook_events

        old = WebhookEvent.objects.create(
            stripe_event_id="evt_old", event_type="test", payload={},
        )
        WebhookEvent.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=91)
        )
        recent = WebhookEvent.objects.create(
            stripe_event_id="evt_recent", event_type="test", payload={},
        )

        cleanup_webhook_events()

        self.assertFalse(WebhookEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(WebhookEvent.objects.filter(pk=recent.pk).exists())


class ProcessScheduledEventsTest(TestCase):

    def test_processes_due_events(self):
        from core.tasks import process_scheduled_events

        event = ScheduledEvent.objects.create(
            event_type=EventType.SUBSCRIPTION_REMINDER,
            execute_at=timezone.now() - timedelta(minutes=1),
            payload={"subscription_id": 1, "days": 7},
        )

        with patch("core.tasks.dispatch_event", return_value=1):
            process_scheduled_events()

        event.refresh_from_db()
        self.assertTrue(event.processed)
        self.assertEqual(event.attempts, 1)

    @override_settings(SCHEDULED_EVENT_MAX_ATTEMPTS=2)
    def test_skips_events_at_max_attempts(self):
        from core.tasks import process_scheduled_events

        event = ScheduledEvent.objects.create(
            event_type=EventType.SUBSCRIPTION_REMINDER,
            execute_at=timezone.now() - timedelta(minutes=1),
            payload={},
            attempts=2,
        )

        with patch("core.tasks.dispatch_event") as mock_dispatch:
            process_scheduled_events()
            mock_dispatch.assert_not_called()

        event.refresh_from_db()
        self.assertFalse(event.processed)

    def test_records_error_on_failure(self):
        from core.tasks import process_scheduled_events

        event = ScheduledEvent.objects.create(
            event_type=EventType.SUBSCRIPTION_REMINDER,
            execute_at=timezone.now() - timedelta(minutes=1),
            payload={},
        )

        with patch("core.tasks.dispatch_event", side_effect=ValueError("boom")):
            process_scheduled_events()

        event.refresh_from_db()
        self.assertFalse(event.processed)
        self.assertEqual(event.attempts, 1)
        self.assertIn("boom", event.last_error)


class WebhookExceptionTest(TestCase):

    def test_webhook_skip_has_correct_flags(self):
        from core.exceptions import WebhookSkip
        e = WebhookSkip("test skip")
        self.assertTrue(e.expected)
        self.assertFalse(e.retryable)
        self.assertEqual(e.key, "webhook@skipped")

    def test_webhook_retry_has_correct_flags(self):
        from core.exceptions import WebhookRetry
        e = WebhookRetry("test retry")
        self.assertFalse(e.expected)
        self.assertTrue(e.retryable)
        self.assertEqual(e.key, "webhook@retry")

    def test_webhook_infrastructure_error_is_retryable(self):
        from core.exceptions import WebhookInfrastructureError
        e = WebhookInfrastructureError("DB down")
        self.assertTrue(e.retryable)
        self.assertEqual(e.key, "webhook@infrastructure")

    def test_repr_is_meaningful(self):
        from core.exceptions import WebhookSkip
        e = WebhookSkip("test", context={"sub": "sub_123"})
        r = repr(e)
        self.assertIn("WebhookSkip", r)
        self.assertIn("retryable=False", r)
