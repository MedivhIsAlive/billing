from django.db import models
from accounts.models import Customer


class PurchaseType(models.TextChoices):
    SUBSCRIPTION_NEW = "subscription_new", "New Subscription"
    SUBSCRIPTION_RENEWAL = "subscription_renewal", "Subscription Renewal"
    SUBSCRIPTION_UPGRADE = "subscription_upgrade", "Subscription Upgrade"
    SUBSCRIPTION_DOWNGRADE = "subscription_downgrade", "Subscription Downgrade"
    ONE_TIME = "one_time", "One-Time Purchase"


class PurchaseStatus(models.TextChoices):
    PAID = "paid", "Paid"
    REFUNDED = "refunded", "Refunded"
    PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"
    DISPUTED = "disputed", "Disputed"


class Purchase(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="purchases")

    purchase_type = models.CharField(max_length=30, choices=PurchaseType.choices, db_index=True)

    status = models.CharField(max_length=20, choices=PurchaseStatus.choices, default=PurchaseStatus.PAID, db_index=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_refunded = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    product_name = models.CharField(max_length=255)

    stripe_price_id = models.CharField(max_length=255, db_index=True, blank=True, default="")
    stripe_invoice_id = models.CharField(max_length=255, db_index=True, blank=True, default="")
    stripe_checkout_session_id = models.CharField(max_length=255, db_index=True, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=255, db_index=True, blank=True, default="")
    stripe_charge_id = models.CharField(max_length=255, db_index=True, blank=True, default="")

    dispute_reason = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchases"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["customer", "purchase_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["stripe_invoice_id", "stripe_price_id"],
                condition=~models.Q(stripe_invoice_id=""),
                name="unique_purchase_per_invoice_line",
            ),
            models.UniqueConstraint(
                fields=["stripe_checkout_session_id"],
                condition=~models.Q(stripe_checkout_session_id=""),
                name="unique_purchase_per_checkout_session",
            ),
        ]

    def __str__(self):
        return f"{self.customer} - {self.product_name} - {self.amount}"

    @property
    def net_amount(self):
        return self.amount - self.amount_refunded

    def refund(self, amount=None):
        refund_amount = self.amount if amount is None else amount

        updated = (
            Purchase.objects
            .filter(pk=self.pk)
            .update(
                amount_refunded=models.F("amount_refunded") + refund_amount,
                status=models.Case(
                    models.When(
                        amount_refunded__gte=models.F("amount") - refund_amount,
                        then=models.Value(PurchaseStatus.REFUNDED),
                    ),
                    default=models.Value(PurchaseStatus.PARTIALLY_REFUNDED),
                ),
            )
        )

        if updated:
            self.refresh_from_db(fields=["amount_refunded", "status"])

    def mark_disputed(self, reason: str = ""):
        self.status = PurchaseStatus.DISPUTED
        self.dispute_reason = reason
        self.save(update_fields=["status", "dispute_reason", "updated_at"])
