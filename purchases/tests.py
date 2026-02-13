from decimal import Decimal

from django.test import TestCase

from purchases.models import Purchase, PurchaseType, PurchaseStatus
from testing_utils import make_customer


class PurchaseRefundTest(TestCase):

    def setUp(self):
        self.customer = make_customer()

    def test_full_refund(self):
        p = Purchase.objects.create(
            customer=self.customer,
            purchase_type=PurchaseType.ONE_TIME,
            amount=Decimal("29.99"),
            product_name="Pro Plan",
            stripe_price_id="price_pro",
            stripe_invoice_id="in_test",
        )
        p.refund()
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.REFUNDED)
        self.assertEqual(p.amount_refunded, Decimal("29.99"))
        self.assertEqual(p.net_amount, Decimal("0.00"))

    def test_partial_refund(self):
        p = Purchase.objects.create(
            customer=self.customer,
            purchase_type=PurchaseType.ONE_TIME,
            amount=Decimal("29.99"),
            product_name="Pro Plan",
            stripe_price_id="price_pro",
            stripe_invoice_id="in_test",
        )
        p.refund(Decimal("10.00"))
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.PARTIALLY_REFUNDED)
        self.assertEqual(p.amount_refunded, Decimal("10.00"))
        self.assertEqual(p.net_amount, Decimal("19.99"))

    def test_mark_disputed(self):
        p = Purchase.objects.create(
            customer=self.customer,
            purchase_type=PurchaseType.ONE_TIME,
            amount=Decimal("49.99"),
            product_name="Widget",
            stripe_charge_id="ch_disp",
        )
        p.mark_disputed(reason="fraudulent")
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.DISPUTED)
        self.assertEqual(p.dispute_reason, "fraudulent")
