from datetime import timedelta
from typing import Optional

from django.db import transaction, models
from django.utils import timezone

from entitlement.models import Entitlement, GrantedBy


def has_access(customer, feature: str) -> bool:
    return (
        Entitlement.objects.filter(customer=customer, feature=feature, is_active=True)
        .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))
        .filter(models.Q(usage_limit__isnull=True) | models.Q(usage_count__lt=models.F("usage_limit")))
        .exists()
    )


def get_active_entitlements(customer) -> list[str]:
    return list(
        Entitlement.objects.filter(customer=customer, is_active=True)
        .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))
        .values_list("feature", flat=True)
        .distinct()
    )


def grant(
    customer,
    feature: str,
    granted_by: str = GrantedBy.MANUAL,
    subscription=None,
    expires_at=None,
    usage_limit: Optional[int] = None,
) -> Entitlement:
    return Entitlement.objects.create(
        customer=customer,
        feature=feature,
        granted_by=granted_by,
        subscription=subscription,
        expires_at=expires_at,
        usage_limit=usage_limit,
    )


def grant_trial(customer, feature: str, days: int = 14) -> Entitlement:
    return grant(
        customer=customer, feature=feature, granted_by=GrantedBy.TRIAL, expires_at=timezone.now() + timedelta(days=days)
    )


@transaction.atomic
def revoke(customer, feature: str, reason: str = "") -> int:
    entitlements = Entitlement.objects.filter(customer=customer, feature=feature, is_active=True)
    count = entitlements.count()

    for ent in entitlements:
        ent.revoke(reason)

    return count


def revoke_for_subscription(subscription, reason: str = "Subscription ended") -> int:
    return Entitlement.objects.filter(subscription=subscription, is_active=True).revoke_all(reason=reason)  # pyright: ignore[reportAttributeAccessIssue]


@transaction.atomic
def sync_from_subscription(subscription, features: list[str]) -> None:
    current = set(
        Entitlement.objects.filter(subscription=subscription, is_active=True).values_list("feature", flat=True)
    )

    desired = set(features)

    for feature in desired - current:
        Entitlement.objects.create(
            customer=subscription.customer,
            feature=feature,
            granted_by=GrantedBy.SUBSCRIPTION,
            subscription=subscription,
        )

    for feature in current - desired:
        Entitlement.objects.filter(subscription=subscription, feature=feature, is_active=True).update(
            is_active=False, revoked_at=timezone.now(), revoke_reason="Feature removed from subscription"
        )
