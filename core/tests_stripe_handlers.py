from decimal import Decimal

from django.test import TestCase

from accounts.models import Customer
from core.exceptions import WebhookSkip, WebhookRetry
from subscriptions.models import Subscription, SubscriptionStatus
from entitlement.models import Entitlement
from purchases.models import Purchase, PurchaseStatus

from subscriptions.stripe_handlers import (
    HandleSubscriptionCreated,
    HandleSubscriptionUpdated,
    HandleSubscriptionDeleted,
    HandleSubscriptionPaused,
    HandleSubscriptionResumed,
)
from purchases.stripe_handlers import (
    HandleInvoicePaid,
    HandleCheckoutSessionCompleted,
    HandleChargeRefunded,
    HandleChargeDisputeCreated,
    HandlePaymentIntentFailed,
)
from accounts.stripe_handlers import HandleCustomerUpdated
from testing_utils import (
    make_customer,
    make_subscription,
    make_stripe_subscription_data,
    make_stripe_invoice_data,
    make_stripe_charge_data,
    make_stripe_checkout_session_data,
    make_stripe_dispute_data,
    make_stripe_customer_data,
    make_stripe_payment_intent_data,
)


class HandleSubscriptionCreatedTest(TestCase):

    def test_creates_subscription_and_entitlements(self):
        customer = make_customer(stripe_customer_id="cus_create")
        data = make_stripe_subscription_data(
            sub_id="sub_new",
            customer_id="cus_create",
            price_id="price_pro_monthly",
            status="active",
        )
        HandleSubscriptionCreated.handle(data)

        sub = Subscription.objects.get(stripe_subscription_id="sub_new")
        self.assertEqual(sub.customer, customer)
        self.assertEqual(sub.status, "active")
        self.assertEqual(sub.stripe_price_id, "price_pro_monthly")

        features = set(
            Entitlement.objects.filter(subscription=sub, is_active=True)
            .values_list("feature", flat=True)
        )
        self.assertEqual(features, {"pro", "api_access", "priority_support"})

    def test_idempotent_on_duplicate(self):
        make_customer(stripe_customer_id="cus_idem")
        data = make_stripe_subscription_data(sub_id="sub_idem", customer_id="cus_idem")
        HandleSubscriptionCreated.handle(data)
        HandleSubscriptionCreated.handle(data)
        self.assertEqual(Subscription.objects.filter(stripe_subscription_id="sub_idem").count(), 1)

    def test_raises_webhook_retry_on_unknown_customer(self):
        data = make_stripe_subscription_data(customer_id="cus_unknown")
        with self.assertRaises(WebhookRetry):
            HandleSubscriptionCreated.handle(data)


class HandleSubscriptionUpdatedTest(TestCase):

    def test_updates_subscription_fields(self):
        customer = make_customer(stripe_customer_id="cus_upd")
        sub = make_subscription(customer=customer, stripe_subscription_id="sub_upd")

        data = make_stripe_subscription_data(
            sub_id="sub_upd", customer_id="cus_upd",
            price_id="price_basic_monthly", status="active",
        )
        HandleSubscriptionUpdated.handle(data)

        sub.refresh_from_db()
        self.assertEqual(sub.stripe_price_id, "price_basic_monthly")

    def test_revokes_entitlements_on_cancel(self):
        customer = make_customer(stripe_customer_id="cus_cancel")
        sub = make_subscription(customer=customer, stripe_subscription_id="sub_cancel")
        Entitlement.objects.create(customer=customer, subscription=sub, feature="pro")

        data = make_stripe_subscription_data(
            sub_id="sub_cancel", customer_id="cus_cancel", status="canceled",
        )
        HandleSubscriptionUpdated.handle(data)

        sub.refresh_from_db()
        self.assertEqual(sub.status, "canceled")
        self.assertEqual(Entitlement.objects.filter(subscription=sub, is_active=True).count(), 0)

    def test_raises_webhook_skip_for_unknown_subscription(self):
        data = make_stripe_subscription_data(sub_id="sub_nonexistent")
        with self.assertRaises(WebhookSkip):
            HandleSubscriptionUpdated.handle(data)


class HandleSubscriptionDeletedTest(TestCase):

    def test_cancels_and_revokes(self):
        customer = make_customer(stripe_customer_id="cus_del")
        sub = make_subscription(customer=customer, stripe_subscription_id="sub_del")
        Entitlement.objects.create(customer=customer, subscription=sub, feature="pro")

        data = make_stripe_subscription_data(sub_id="sub_del", customer_id="cus_del")
        HandleSubscriptionDeleted.handle(data)

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.CANCELED)
        self.assertEqual(Entitlement.objects.filter(subscription=sub, is_active=True).count(), 0)


class HandleSubscriptionPausedTest(TestCase):

    def test_pauses_and_revokes_entitlements(self):
        customer = make_customer(stripe_customer_id="cus_pause")
        sub = make_subscription(customer=customer, stripe_subscription_id="sub_pause")
        Entitlement.objects.create(customer=customer, subscription=sub, feature="pro")
        Entitlement.objects.create(customer=customer, subscription=sub, feature="api_access")

        data = make_stripe_subscription_data(sub_id="sub_pause", customer_id="cus_pause")
        HandleSubscriptionPaused.handle(data)

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.PAUSED)
        self.assertIsNotNone(sub.paused_at)
        self.assertEqual(Entitlement.objects.filter(subscription=sub, is_active=True).count(), 0)

    def test_raises_webhook_skip_for_unknown_subscription(self):
        data = make_stripe_subscription_data(sub_id="sub_unknown_pause")
        with self.assertRaises(WebhookSkip):
            HandleSubscriptionPaused.handle(data)


class HandleSubscriptionResumedTest(TestCase):

    def test_resumes_and_resyncs_entitlements(self):
        customer = make_customer(stripe_customer_id="cus_resume")
        sub = make_subscription(
            customer=customer,
            stripe_subscription_id="sub_resume",
            status=SubscriptionStatus.PAUSED,
        )
        self.assertEqual(Entitlement.objects.filter(subscription=sub, is_active=True).count(), 0)

        data = make_stripe_subscription_data(
            sub_id="sub_resume", customer_id="cus_resume",
            price_id="price_pro_monthly", status="active",
        )
        HandleSubscriptionResumed.handle(data)

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertIsNotNone(sub.resumed_at)
        self.assertIsNone(sub.paused_at)

        features = set(
            Entitlement.objects.filter(subscription=sub, is_active=True)
            .values_list("feature", flat=True)
        )
        self.assertEqual(features, {"pro", "api_access", "priority_support"})

    def test_raises_webhook_skip_for_unknown_subscription(self):
        data = make_stripe_subscription_data(sub_id="sub_unknown_resume")
        with self.assertRaises(WebhookSkip):
            HandleSubscriptionResumed.handle(data)


class HandleInvoicePaidTest(TestCase):

    def test_creates_purchase(self):
        customer = make_customer(stripe_customer_id="cus_inv")
        data = make_stripe_invoice_data(
            invoice_id="in_paid", customer_id="cus_inv",
            billing_reason="subscription_create",
        )
        HandleInvoicePaid.handle(data)

        purchase = Purchase.objects.get(stripe_invoice_id="in_paid")
        self.assertEqual(purchase.customer, customer)
        self.assertEqual(purchase.amount, Decimal("29.99"))
        self.assertEqual(purchase.purchase_type, "subscription_new")

    def test_idempotent_on_duplicate_invoice(self):
        make_customer(stripe_customer_id="cus_idem_inv")
        data = make_stripe_invoice_data(invoice_id="in_dup", customer_id="cus_idem_inv")
        HandleInvoicePaid.handle(data)
        HandleInvoicePaid.handle(data)
        self.assertEqual(Purchase.objects.filter(stripe_invoice_id="in_dup").count(), 1)

    def test_skips_unknown_customer(self):
        data = make_stripe_invoice_data(customer_id="cus_ghost")
        HandleInvoicePaid.handle(data)
        self.assertEqual(Purchase.objects.count(), 0)


class HandleCheckoutSessionCompletedTest(TestCase):

    def test_creates_one_time_purchase(self):
        customer = make_customer(stripe_customer_id="cus_checkout")
        data = make_stripe_checkout_session_data(
            session_id="cs_onetimetest",
            customer_id="cus_checkout",
            mode="payment",
            payment_status="paid",
            amount_total=4999,
            payment_intent="pi_checkout",
            metadata={"product_name": "Setup Fee"},
        )
        HandleCheckoutSessionCompleted.handle(data)

        purchase = Purchase.objects.get(stripe_checkout_session_id="cs_onetimetest")
        self.assertEqual(purchase.customer, customer)
        self.assertEqual(purchase.amount, Decimal("49.99"))
        self.assertEqual(purchase.product_name, "Setup Fee")
        self.assertEqual(purchase.purchase_type, "one_time")
        self.assertEqual(purchase.stripe_payment_intent_id, "pi_checkout")

    def test_skips_subscription_mode(self):
        make_customer(stripe_customer_id="cus_sub_checkout")
        data = make_stripe_checkout_session_data(
            session_id="cs_submode",
            customer_id="cus_sub_checkout",
            mode="subscription",
            subscription="sub_from_checkout",
        )
        HandleCheckoutSessionCompleted.handle(data)
        self.assertEqual(Purchase.objects.count(), 0)

    def test_skips_unpaid_session(self):
        make_customer(stripe_customer_id="cus_unpaid_checkout")
        data = make_stripe_checkout_session_data(
            session_id="cs_unpaid",
            customer_id="cus_unpaid_checkout",
            payment_status="unpaid",
        )
        HandleCheckoutSessionCompleted.handle(data)
        self.assertEqual(Purchase.objects.count(), 0)

    def test_idempotent_on_duplicate_session(self):
        make_customer(stripe_customer_id="cus_dup_checkout")
        data = make_stripe_checkout_session_data(
            session_id="cs_idem",
            customer_id="cus_dup_checkout",
        )
        HandleCheckoutSessionCompleted.handle(data)
        HandleCheckoutSessionCompleted.handle(data)
        self.assertEqual(Purchase.objects.filter(stripe_checkout_session_id="cs_idem").count(), 1)

    def test_raises_webhook_skip_for_no_customer(self):
        data = make_stripe_checkout_session_data(customer_id=None)
        with self.assertRaises(WebhookSkip):
            HandleCheckoutSessionCompleted.handle(data)

    def test_raises_webhook_skip_for_unknown_customer(self):
        data = make_stripe_checkout_session_data(customer_id="cus_ghost_checkout")
        with self.assertRaises(WebhookSkip):
            HandleCheckoutSessionCompleted.handle(data)

    def test_default_product_name_when_no_metadata(self):
        make_customer(stripe_customer_id="cus_nometa")
        data = make_stripe_checkout_session_data(
            session_id="cs_nometa",
            customer_id="cus_nometa",
            metadata={},
        )
        HandleCheckoutSessionCompleted.handle(data)
        purchase = Purchase.objects.get(stripe_checkout_session_id="cs_nometa")
        self.assertEqual(purchase.product_name, "One-time purchase")


class HandleChargeRefundedTest(TestCase):

    def test_refunds_purchase(self):
        customer = make_customer(stripe_customer_id="cus_ref")
        Purchase.objects.create(
            customer=customer, purchase_type="one_time",
            amount=Decimal("29.99"), product_name="Pro",
            stripe_price_id="price_pro", stripe_invoice_id="in_refund",
        )

        data = make_stripe_charge_data(invoice_id="in_refund", amount_refunded=2999)
        HandleChargeRefunded.handle(data)

        purchase = Purchase.objects.get(stripe_invoice_id="in_refund")
        self.assertEqual(purchase.status, PurchaseStatus.REFUNDED)

    def test_skips_charge_without_invoice(self):
        data = {"id": "ch_noinv", "invoice": None, "amount_refunded": 0}
        HandleChargeRefunded.handle(data)

    def test_raises_webhook_skip_for_unknown_invoice(self):
        data = make_stripe_charge_data(invoice_id="in_ghost")
        with self.assertRaises(WebhookSkip):
            HandleChargeRefunded.handle(data)


class HandleChargeDisputeCreatedTest(TestCase):

    def test_marks_purchase_disputed_by_charge_id(self):
        customer = make_customer(stripe_customer_id="cus_disp")
        Purchase.objects.create(
            customer=customer, purchase_type="one_time",
            amount=Decimal("29.99"), product_name="Widget",
            stripe_charge_id="ch_disputed",
            stripe_payment_intent_id="pi_disputed",
        )

        data = make_stripe_dispute_data(
            charge_id="ch_disputed",
            reason="fraudulent",
            payment_intent="pi_disputed",
        )
        HandleChargeDisputeCreated.handle(data)

        purchase = Purchase.objects.get(stripe_charge_id="ch_disputed")
        self.assertEqual(purchase.status, PurchaseStatus.DISPUTED)
        self.assertEqual(purchase.dispute_reason, "fraudulent")

    def test_finds_purchase_by_payment_intent_fallback(self):
        customer = make_customer(stripe_customer_id="cus_disp_pi")
        Purchase.objects.create(
            customer=customer, purchase_type="one_time",
            amount=Decimal("15.00"), product_name="Widget",
            stripe_payment_intent_id="pi_fallback",
        )

        data = make_stripe_dispute_data(
            charge_id="ch_nomatch",
            payment_intent="pi_fallback",
            reason="product_not_received",
        )
        HandleChargeDisputeCreated.handle(data)

        purchase = Purchase.objects.get(stripe_payment_intent_id="pi_fallback")
        self.assertEqual(purchase.status, PurchaseStatus.DISPUTED)
        self.assertEqual(purchase.dispute_reason, "product_not_received")

    def test_raises_webhook_skip_when_no_purchase_found(self):
        data = make_stripe_dispute_data(
            charge_id="ch_ghost", payment_intent="pi_ghost",
        )
        with self.assertRaises(WebhookSkip):
            HandleChargeDisputeCreated.handle(data)


class HandleCustomerUpdatedTest(TestCase):

    def test_syncs_billing_email(self):
        customer = make_customer(stripe_customer_id="cus_cusupd")
        self.assertEqual(customer.billing_email, "")

        data = make_stripe_customer_data(
            customer_id="cus_cusupd",
            email="newemail@example.com",
        )
        HandleCustomerUpdated.handle(data)

        customer.refresh_from_db()
        self.assertEqual(customer.billing_email, "newemail@example.com")

    def test_no_op_when_email_unchanged(self):
        customer = make_customer(stripe_customer_id="cus_cusupd_noop")
        customer.billing_email = "same@example.com"
        customer.save()

        data = make_stripe_customer_data(
            customer_id="cus_cusupd_noop",
            email="same@example.com",
        )
        HandleCustomerUpdated.handle(data)

    def test_skips_unknown_customer(self):
        data = make_stripe_customer_data(customer_id="cus_ghost_cusupd")
        HandleCustomerUpdated.handle(data)
