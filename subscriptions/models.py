from django.db import models


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past Due"
    CANCELED = "canceled", "Canceled"
    INCOMPLETE = "incomplete", "Incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired", "Incomplete Expired"
    TRIALING = "trialing", "Trialing"
    UNPAID = "unpaid", "Unpaid"
    PAUSED = "paused", "Paused"


class Subscription(models.Model):
    customer = models.ForeignKey("accounts.Customer", on_delete=models.PROTECT, related_name="subscriptions")

    stripe_subscription_id = models.CharField(max_length=255, unique=True, db_index=True)
    stripe_price_id = models.CharField(max_length=255, db_index=True, help_text="Current price ID from Stripe")
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, db_index=True)

    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField(db_index=True)

    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscriptions"
        indexes = [
            models.Index(fields=["customer", "status"]),
        ]

    def __str__(self):
        return f"{self.customer} - {self.stripe_price_id} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.PAST_DUE,  # Grace period
        )
