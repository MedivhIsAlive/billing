from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from accounts.models import Customer
from payments.views import get_billing_status, get_purchase_history
from payments.services import (
    get_or_create_stripe_customer,
    get_billing_status_for_user,
    get_purchase_history_for_user,
    get_available_products,
    invalidate_product_cache,
)
from testing_utils import make_customer, make_subscription
from purchases.models import Purchase, PurchaseType
from entitlement.models import Entitlement


User = get_user_model()


class GetBillingStatusServiceTest(TestCase):

    def test_no_customer_returns_empty(self):
        user = User.objects.create_user(username="testuser", email="t@test.com", password="pass")
        result = get_billing_status_for_user(user)
        self.assertFalse(result["has_subscription"])
        self.assertIsNone(result["subscription"])
        self.assertEqual(result["entitlements"], [])

    def test_with_active_subscription(self):
        user = User.objects.create_user(username="testuser2", email="t2@test.com", password="pass")
        customer = make_customer(user=user, stripe_customer_id="cus_billing")
        sub = make_subscription(customer=customer)
        Entitlement.objects.create(customer=customer, feature="pro")

        result = get_billing_status_for_user(user)
        self.assertTrue(result["has_subscription"])
        self.assertEqual(result["subscription"]["status"], "active")
        self.assertIn("pro", result["entitlements"])


class GetPurchaseHistoryServiceTest(TestCase):

    def test_no_customer_returns_empty(self):
        user = User.objects.create_user(username="testuser3", email="t3@test.com", password="pass")
        result = get_purchase_history_for_user(user)
        self.assertEqual(result, [])

    def test_with_purchases(self):
        user = User.objects.create_user(username="testuser4", email="t4@test.com", password="pass")
        customer = make_customer(user=user, stripe_customer_id="cus_hist")
        Purchase.objects.create(
            customer=customer,
            purchase_type=PurchaseType.ONE_TIME,
            amount=Decimal("19.99"),
            product_name="Widget",
            stripe_price_id="price_w",
            stripe_invoice_id="in_w",
        )
        result = get_purchase_history_for_user(user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["product_name"], "Widget")


class GetOrCreateStripeCustomerTest(TestCase):

    @patch("payments.services.stripe.Customer.create")
    def test_creates_stripe_customer_when_missing(self, mock_stripe_create):
        mock_stripe_create.return_value = MagicMock(id="cus_new_stripe")
        user = User.objects.create_user(username="newuser", email="new@test.com", password="pass")

        customer = get_or_create_stripe_customer(user)

        self.assertEqual(customer.stripe_customer_id, "cus_new_stripe")
        mock_stripe_create.assert_called_once()

    def test_returns_existing_customer(self):
        user = User.objects.create_user(username="existing", email="existing@test.com", password="pass")
        Customer.objects.create(user=user, stripe_customer_id="cus_existing")

        customer = get_or_create_stripe_customer(user)

        self.assertEqual(customer.stripe_customer_id, "cus_existing")


class GetAvailableProductsTest(TestCase):

    @patch("payments.services.stripe.Price.list")
    @patch("payments.services.stripe.Product.list")
    def test_caches_results(self, mock_products, mock_prices):
        mock_products.return_value = MagicMock(data=[
            SimpleNamespace(
                id="prod_1",
                name="Pro",
                description="Pro plan",
                active=True
            ),
        ])

        mock_prices.return_value = MagicMock(data=[
            SimpleNamespace(
                id="price_1",
                product="prod_1",
                unit_amount=2999,
                currency="usd",
                recurring=SimpleNamespace(interval="month"),
                active=True
            ),
        ])
        invalidate_product_cache()

        result1 = get_available_products()
        self.assertEqual(len(result1), 1)
        self.assertEqual(mock_products.call_count, 1)

        result2 = get_available_products()
        self.assertEqual(len(result2), 1)
        self.assertEqual(mock_products.call_count, 1)

        invalidate_product_cache()
        _ = get_available_products()
        self.assertEqual(mock_products.call_count, 2)


class BillingStatusViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="viewtest", email="vt@test.com", password="pass")

    def test_view_returns_service_result(self):
        request = self.factory.get("/api/payments/status/")
        request.user = self.user
        response = get_billing_status(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["has_subscription"])
