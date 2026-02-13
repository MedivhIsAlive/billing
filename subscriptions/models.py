from hmac import new
import logging
from django.db import models
from django.utils import timezone

log = logging.getLogger("billing.subscriptions")


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past Due"
    CANCELED = "canceled", "Canceled"
    INCOMPLETE = "incomplete", "Incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired", "Incomplete Expired"
    TRIALING = "trialing", "Trialing"
    UNPAID = "unpaid", "Unpaid"
    PAUSED = "paused", "Paused"


EXPECTED_TRANSITIONS: dict[str, set[str]] = {
    SubscriptionStatus.ACTIVE: {SubscriptionStatus.PAST_DUE, SubscriptionStatus.CANCELED, SubscriptionStatus.PAUSED, SubscriptionStatus.UNPAID},
    SubscriptionStatus.TRIALING: {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE, SubscriptionStatus.CANCELED, SubscriptionStatus.PAUSED},
    SubscriptionStatus.PAST_DUE: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED, SubscriptionStatus.UNPAID},
    SubscriptionStatus.PAUSED: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED},
    SubscriptionStatus.INCOMPLETE: {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.INCOMPLETE_EXPIRED, SubscriptionStatus.CANCELED},
    SubscriptionStatus.INCOMPLETE_EXPIRED: set(),
    SubscriptionStatus.UNPAID: {SubscriptionStatus.CANCELED},
    SubscriptionStatus.CANCELED: set(),
}


class Subscription(models.Model):
    customer = models.ForeignKey("accounts.Customer", on_delete=models.PROTECT, related_name="subscriptions")

    stripe_subscription_id = models.CharField(max_length=255, unique=True, db_index=True)
    stripe_price_id = models.CharField(max_length=255, db_index=True)

    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.INCOMPLETE,
        db_index=True,
    )

    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField(db_index=True)

    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)

    paused_at = models.DateTimeField(null=True, blank=True)
    resumed_at = models.DateTimeField(null=True, blank=True)

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
            SubscriptionStatus.PAST_DUE,
        )

    def cancel(self):
        self.apply_new_status(SubscriptionStatus.CANCELED)
        self.canceled_at = timezone.now()
        self.save(update_fields=["status", "canceled_at", "updated_at"])

    def pause(self):
        self.apply_new_status(SubscriptionStatus.PAUSED)
        self.paused_at = timezone.now()
        self.save(update_fields=["status", "paused_at", "updated_at"])

    def apply_new_status(self, new_status: str):
        if new_status not in EXPECTED_TRANSITIONS.get(self.status, set()):
            log.warning(f"Unexpected transition {self.status} → {new_status} for {self.stripe_subscription_id}")
        self.status = new_status

