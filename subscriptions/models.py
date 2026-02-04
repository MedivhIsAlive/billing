from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Status(models.TextChoices):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    CANCELED = "canceled"


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, null=False, blank=False)
    price_monthly = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    stripe_product_id = models.CharField(max_length=255, unique=True, null=True)
    stripe_price_id = models.CharField(max_length=255, unique=True, null=True)

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.is_active=})"

    class Meta:
        ordering = ["price_monthly"]
        indexes = [
            models.Index(fields=["is_active", "created_at"]),
        ]


class Subscription(models.Model):
    # the only reason this exists is to satisfy my lsp, i just dont like highlighting sry
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=Status.choices)
    current_period_start = models.DateTimeField(
        null=True,
        blank=True,
    )
    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
    )
    cancel_at_period_end = models.BooleanField(default=False)
    display_currency = models.CharField(max_length=3, default="USD")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    stripe_subscription_id = models.CharField(max_length=255, unique=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "current_period_end"]),
            models.Index(fields=["status", "current_period_end"]),
        ]


class SubscriptionHistory(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices)
