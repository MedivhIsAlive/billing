import logging

from django.conf import settings
from django.utils import timezone
import stripe

from accounts.models import Customer
from core.exceptions import WebhookSkip, WebhookRetry
from core.stripe.event_handler import WebhookHandler
from core.stripe.models import StripeSubscription
from entitlement.services import sync_from_subscription, revoke_for_subscription
from subscriptions.models import Subscription, SubscriptionStatus

log = logging.getLogger("billing.subscriptions.stripe_handlers")


def _get_features_for_price(price_id: str) -> list[str]:
    return settings.STRIPE_PRICE_TO_FEATURES.get(price_id, [])


def ensure_valid_subscription_model(data: dict) -> StripeSubscription:
    event = StripeSubscription.model_validate(data)
    if event.current_period_start is None:
        log.info(f"Subscription {event.id} missing period fields, fetching from Stripe")
        full_sub = stripe.Subscription.retrieve(event.id)
        event = StripeSubscription.model_validate(full_sub)

    if event.current_period_start is None:
        raise WebhookSkip(f"Subscription {event.id} has no period data even after fetch")

    return event


class HandleSubscriptionCreated(WebhookHandler):
    __event__ = "customer.subscription.created"

    @classmethod
    def handle(cls, data: dict):
        event = ensure_valid_subscription_model(data)

        try:
            customer = Customer.objects.get(stripe_customer_id=event.customer)
        except Customer.DoesNotExist:
            raise WebhookRetry(
                f"No customer for stripe_customer_id={event.customer} — may not be synced yet",
                context={"stripe_customer_id": event.customer},
            )

        subscription, created = Subscription.objects.update_or_create(
            stripe_subscription_id=event.id,
            defaults={
                "customer": customer,
                "stripe_price_id": event.price_id,
                "status": event.status,
                "current_period_start": event.current_period_start_dt,
                "current_period_end": event.current_period_end_dt,
                "cancel_at_period_end": event.cancel_at_period_end,
                "trial_start": event.trial_start_dt,
                "trial_end": event.trial_end_dt,
            },
        )

        action = "Created" if created else "Updated (idempotent)"
        log.info(f"{action} subscription {subscription.pk} for customer {customer.pk}")

        if subscription.is_active:
            features = _get_features_for_price(event.price_id)
            sync_from_subscription(subscription, features)


class HandleSubscriptionUpdated(WebhookHandler):
    __event__ = "customer.subscription.updated"

    @classmethod
    def handle(cls, data: dict):
        event = ensure_valid_subscription_model(data)

        try:
            subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
        except Subscription.DoesNotExist:
            raise WebhookSkip(
                f"Subscription {event.id} not found for update",
                context={"stripe_subscription_id": event.id},
            )

        subscription.stripe_price_id = event.price_id
        subscription.current_period_start = event.current_period_start_dt
        subscription.current_period_end = event.current_period_end_dt
        subscription.cancel_at_period_end = event.cancel_at_period_end
        subscription.canceled_at = event.canceled_at_dt
        subscription.trial_start = event.trial_start_dt
        subscription.trial_end = event.trial_end_dt

        if event.status != subscription.status:
            subscription.apply_new_status(event.status)

        subscription.save()

        if subscription.is_active:
            features = _get_features_for_price(event.price_id)
            sync_from_subscription(subscription, features)
        else:
            revoke_for_subscription(
                subscription,
                reason=f"Subscription status changed to: {subscription.status}",
            )


class HandleSubscriptionDeleted(WebhookHandler):
    __event__ = "customer.subscription.deleted"

    @classmethod
    def handle(cls, data: dict):
        event = ensure_valid_subscription_model(data)

        try:
            subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
        except Subscription.DoesNotExist:
            raise WebhookSkip(
                f"Subscription {event.id} not found for delete",
                context={"stripe_subscription_id": event.id},
            )

        subscription.cancel()
        revoke_for_subscription(subscription, reason="Subscription canceled")


class HandleSubscriptionPaused(WebhookHandler):
    __event__ = "customer.subscription.paused"

    @classmethod
    def handle(cls, data: dict):
        event = ensure_valid_subscription_model(data)

        try:
            subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
        except Subscription.DoesNotExist:
            raise WebhookSkip(
                f"Subscription {event.id} not found for pause",
                context={"stripe_subscription_id": event.id},
            )

        subscription.pause()
        revoke_for_subscription(subscription, reason="Subscription paused")
        log.info(f"Paused subscription {subscription.pk}, entitlements revoked")


class HandleSubscriptionResumed(WebhookHandler):
    __event__ = "customer.subscription.resumed"

    @classmethod
    def handle(cls, data: dict):
        event = ensure_valid_subscription_model(data)

        try:
            subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
        except Subscription.DoesNotExist:
            raise WebhookSkip(
                f"Subscription {event.id} not found for resume",
                context={"stripe_subscription_id": event.id},
            )

        subscription.apply_new_status(SubscriptionStatus.ACTIVE)
        subscription.resumed_at = timezone.now()
        subscription.paused_at = None
        subscription.current_period_start = event.current_period_start_dt
        subscription.current_period_end = event.current_period_end_dt
        subscription.save(
            update_fields=[
                "status",
                "resumed_at",
                "paused_at",
                "current_period_start",
                "current_period_end",
                "updated_at",
            ]
        )

        if subscription.is_active:
            features = _get_features_for_price(event.price_id)
            sync_from_subscription(subscription, features)
        log.info(f"Resumed subscription {subscription.pk}, entitlements re-synced")


__all__ = (
    "HandleSubscriptionCreated",
    "HandleSubscriptionUpdated",
    "HandleSubscriptionDeleted",
    "HandleSubscriptionPaused",
    "HandleSubscriptionResumed",
)
