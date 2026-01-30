from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Status(models.TextChoices):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    CANCELLED = "cancelled"


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, null=False, blank=False)
    price_monthly = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    def __str__(self):
        return f"{self.name} ({self.is_active=})"


class Subscription(models.Model):
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=Status.choices)
    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "current_period_end"]),
        ]


class SubscriptionHistory(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices)
