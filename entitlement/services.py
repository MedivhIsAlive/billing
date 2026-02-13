import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from entitlement.models import Entitlement, GrantedBy

log = logging.getLogger("billing.entitlement")


def has_access(customer, feature: str) -> bool:
    return Entitlement.objects.filter(
        customer=customer, feature=feature,
    ).active().exists()


def get_active_entitlements(customer) -> list[str]:
    return list(
        Entitlement.objects.filter(customer=customer).active()
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
    entitlement, created = Entitlement.objects.get_or_create(
        customer=customer,
        feature=feature,
        subscription=subscription,
        defaults={
            "granted_by": granted_by,
            "expires_at": expires_at,
            "usage_limit": usage_limit,
        },
    )
    if not created and not entitlement.is_active:
        entitlement.is_active = True
        entitlement.revoked_at = None
        entitlement.revoke_reason = ""
        entitlement.granted_by = granted_by
        entitlement.expires_at = expires_at
        entitlement.usage_limit = usage_limit
        entitlement.save()
        log.info(f"Re-activated entitlement {feature} for customer {customer.pk}")

    return entitlement


def grant_trial(customer, feature: str, days: int = 14) -> Entitlement:
    return grant(
        customer=customer,
        feature=feature,
        granted_by=GrantedBy.TRIAL,
        expires_at=timezone.now() + timedelta(days=days),
    )


@transaction.atomic
def revoke(customer, feature: str, reason: str = "") -> int:
    entitlements = Entitlement.objects.filter(customer=customer, feature=feature, is_active=True)
    count = entitlements.count()

    if count:
        entitlements.revoke_all(reason)

    return count


def revoke_for_subscription(subscription, reason: str = "Subscription ended") -> int:
    qs = Entitlement.objects.filter(subscription=subscription, is_active=True)
    count = qs.count()
    if count:
        qs.revoke_all(reason=reason)
        log.info(f"Revoked {count} entitlements for subscription {subscription.pk}: {reason}")
    return count


@transaction.atomic
def sync_from_subscription(subscription, features: list[str]) -> None:
    current = set(
        Entitlement.objects.filter(subscription=subscription, is_active=True).values_list("feature", flat=True)
    )

    desired = set(features)

    for feature in desired - current:
        grant(
            customer=subscription.customer,
            feature=feature,
            granted_by=GrantedBy.SUBSCRIPTION,
            subscription=subscription,
        )

    removed = current - desired
    if removed:
        Entitlement.objects.filter(
            subscription=subscription, feature__in=removed, is_active=True,
        ).revoke_all(reason="Feature removed from subscription plan")

    log.info(
        f"Synced entitlements for subscription {subscription.pk}: +{len(desired - current)} -{len(removed)} (desired={desired})"
    )
