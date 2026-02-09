from django.db import models
from django.utils import timezone

from accounts.models import Customer


class GrantedBy(models.TextChoices):
    SUBSCRIPTION = "subscription", "Subscription"
    TRIAL = "trial", "Trial"
    MANUAL = "manual", "Manual Grant"
    PROMO = "promo", "Promotion"
    REFERRAL = "referral", "Referral"
    EMPLOYEE = "employee", "Employee Perk"


class EntitlementQuerySet(models.QuerySet):
    def active(self):
        return (
            self.filter(is_active=True)
            .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))
            .filter(models.Q(usage_limit__isnull=True) | models.Q(usage_count__lt=models.F("usage_limit")))
        )

    def revoke_all(self, reason=""):
        return self.update(is_active=False, revoked_at=timezone.now(), revoke_reason=reason)


class Entitlement(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="entitlements")

    feature = models.CharField(
        max_length=100, db_index=True, help_text="Feature key: 'pro', 'api_access', 'priority_support', etc."
    )

    granted_by = models.CharField(max_length=20, choices=GrantedBy.choices, default=GrantedBy.SUBSCRIPTION)

    expires_at = models.DateTimeField(null=True, blank=True, db_index=True, default=None)

    is_active = models.BooleanField(default=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=255, blank=True)

    usage_limit = models.PositiveIntegerField(
        null=True, blank=True, default=None, help_text="Max usage count. Null = unlimited."
    )
    usage_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EntitlementQuerySet.as_manager()

    class Meta:
        db_table = "entitlements"
        indexes = [
            models.Index(fields=["customer", "feature", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "feature", "subscription"], name="unique_entitlement_per_subscription"
            )
        ]

    def __str__(self):
        status = "active" if self.is_active else "revoked"
        return f"{self.customer} - {self.feature} ({status})"

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False

        if self.expires_at and timezone.now() > self.expires_at:
            return False

        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False

        return True

    def revoke(self, reason: str = "") -> None:
        self.is_active = False
        self.revoked_at = timezone.now()
        self.revoke_reason = reason
        self.save(update_fields=["is_active", "revoked_at", "revoke_reason", "updated_at"])

    def increment_usage(self) -> bool:
        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False

        self.usage_count = models.F("usage_count") + 1
        self.save(update_fields=["usage_count", "updated_at"])
        return True
