import logging

from django.conf import settings
from django.db import transaction, OperationalError
from django.utils import timezone
from django_fsm import TransitionNotAllowed

from accounts.models import Customer
from core.exceptions import WebhookSkip, WebhookRetry
from core.stripe import register_stripe_webhook
from entitlement.services import sync_from_subscription, revoke_for_subscription
from purchases.models import Purchase, PurchaseType
from subscriptions.models import Subscription, SubscriptionStatus

from core.stripe.models import (
    StripeSubscription,
    StripeInvoice,
    StripeCharge,
    StripeCheckoutSession,
    StripeDispute,
    StripeCustomer,
    StripePaymentIntent,
)

log = logging.getLogger("billing.core.stripe.handlers")


def get_features_for_price(price_id: str) -> list[str]:
    return settings.STRIPE_PRICE_TO_FEATURES.get(price_id, [])


def _get_customer_or_skip(stripe_customer_id: str, context: str) -> Customer:
    try:
        return Customer.objects.get(stripe_customer_id=stripe_customer_id)
    except Customer.DoesNotExist:
        raise WebhookSkip(f"No customer found for stripe_customer_id={stripe_customer_id} ({context})")


def _get_customer_or_none(stripe_customer_id: str, context: str) -> Customer | None:
    try:
        return Customer.objects.get(stripe_customer_id=stripe_customer_id)
    except Customer.DoesNotExist:
        log.warning(f"No customer found for stripe_customer_id={stripe_customer_id} ({context})")
        return None


@register_stripe_webhook("customer.subscription.created")
@transaction.atomic
def handle_subscription_created(data: dict):
    event = StripeSubscription.model_validate(data)

    try:
        customer = Customer.objects.get(stripe_customer_id=event.customer)
    except Customer.DoesNotExist:
        raise WebhookRetry(f"No customer found for stripe_customer_id={event.customer} — may not be synced yet")

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
        features = get_features_for_price(event.price_id)
        sync_from_subscription(subscription, features)


@register_stripe_webhook("customer.subscription.updated")
@transaction.atomic
def handle_subscription_updated(data: dict):
    event = StripeSubscription.model_validate(data)

    try:
        subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
    except Subscription.DoesNotExist:
        raise WebhookSkip(f"Subscription {event.id} not found for update event")

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
        features = get_features_for_price(event.price_id)
        sync_from_subscription(subscription, features)
    else:
        revoke_for_subscription(
            subscription,
            reason=f"Subscription status changed to: {subscription.status}",
        )


@register_stripe_webhook("customer.subscription.deleted")
@transaction.atomic
def handle_subscription_deleted(data: dict):
    event = StripeSubscription.model_validate(data)

    try:
        subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
    except Subscription.DoesNotExist:
        raise WebhookSkip(f"Subscription {event.id} not found for delete event")

    subscription.cancel()
    revoke_for_subscription(subscription, reason="Subscription canceled")


@register_stripe_webhook("customer.subscription.paused")
@transaction.atomic
def handle_subscription_paused(data: dict):
    event = StripeSubscription.model_validate(data)

    try:
        subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
    except Subscription.DoesNotExist:
        raise WebhookSkip(f"Subscription {event.id} not found for pause event")

    subscription.pause()
    revoke_for_subscription(subscription, reason="Subscription paused")
    log.info(f"Paused subscription {subscription.pk}, entitlements revoked")


@register_stripe_webhook("customer.subscription.resumed")
@transaction.atomic
def handle_subscription_resumed(data: dict):
    event = StripeSubscription.model_validate(data)

    try:
        subscription = Subscription.objects.select_for_update().get(stripe_subscription_id=event.id)
    except Subscription.DoesNotExist:
        raise WebhookSkip(f"Subscription {event.id} not found for resume event")

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
        features = get_features_for_price(event.price_id)
        sync_from_subscription(subscription, features)
    log.info(f"Resumed subscription {subscription.pk}, entitlements re-synced")


@register_stripe_webhook("invoice.paid")
@transaction.atomic
def handle_invoice_paid(data: dict):
    event = StripeInvoice.model_validate(data)

    customer = _get_customer_or_none(event.customer, f"invoice.paid {event.id}")
    if not customer:
        return

    purchase_type_map = {
        "subscription_create": PurchaseType.SUBSCRIPTION_NEW,
        "subscription_cycle": PurchaseType.SUBSCRIPTION_RENEWAL,
        "subscription_update": PurchaseType.SUBSCRIPTION_UPGRADE,
    }
    purchase_type = purchase_type_map.get(event.billing_reason or "", PurchaseType.ONE_TIME)

    for line in event.lines.data:
        purchase, created = Purchase.objects.update_or_create(
            stripe_invoice_id=event.id,
            stripe_price_id=line.price_id,
            defaults={
                "customer": customer,
                "purchase_type": purchase_type,
                "amount": line.amount_dollars,
                "product_name": line.description,
            },
        )


@register_stripe_webhook("checkout.session.completed")
@transaction.atomic
def handle_checkout_session_completed(data: dict):
    event = StripeCheckoutSession.model_validate(data)

    if event.mode != "payment":
        log.info(f"Checkout session {event.id} completed (mode={event.mode}), handled by subscription webhooks")
        return

    if event.payment_status != "paid":
        log.info(f"Checkout session {event.id} not yet paid (status={event.payment_status}), skipping")
        return

    if not event.customer:
        raise WebhookSkip(f"Checkout session {event.id} has no customer")

    customer = _get_customer_or_skip(event.customer, f"checkout.session.completed {event.id}")

    if Purchase.objects.filter(stripe_checkout_session_id=event.id).exists():
        log.info(f"Purchase already exists for checkout session {event.id}, skipping")
        return

    _ = Purchase.objects.create(
        customer=customer,
        purchase_type=PurchaseType.ONE_TIME,
        amount=event.amount_total_dollars or 0,
        product_name=event.metadata.get("product_name", "One-time purchase"),
        stripe_checkout_session_id=event.id,
        stripe_payment_intent_id=event.payment_intent or "",
    )

    log.info(
        f"Created one-time purchase from checkout session {event.id} for customer {customer.pk} (${event.amount_total_dollars})"
    )


@register_stripe_webhook("charge.refunded")
@transaction.atomic
def handle_charge_refunded(data: dict):
    event = StripeCharge.model_validate(data)

    if not event.invoice:
        log.info(f"Charge {event.id} refunded but has no invoice, skipping")
        return

    purchases = Purchase.objects.filter(stripe_invoice_id=event.invoice)

    if not purchases.exists():
        raise WebhookSkip(f"No purchase found for invoice {event.invoice} on refund")

    for purchase in purchases:
        purchase.refund(event.amount_refunded_dollars)


@register_stripe_webhook("charge.dispute.created")
@transaction.atomic
def handle_charge_dispute_created(data: dict):
    event = StripeDispute.model_validate(data)

    purchase = None

    if event.charge:
        purchase = Purchase.objects.filter(stripe_charge_id=event.charge).first()

    if not purchase and event.payment_intent:
        purchase = Purchase.objects.filter(stripe_payment_intent_id=event.payment_intent).first()

    if not purchase:
        raise WebhookSkip(
            f"No purchase found for dispute {event.id} (charge={event.charge}, pi={event.payment_intent})"
        )

    purchase.mark_disputed(reason=event.reason)
    log.warning(
        f"Purchase {purchase.pk} marked as disputed: dispute={event.id}, reason={event.reason}, amount=${event.amount_dollars}"
    )


@register_stripe_webhook("payment_intent.payment_failed")
def handle_payment_intent_failed(data: dict):
    event = StripePaymentIntent.model_validate(data)
    log.warning(
        f"PaymentIntent failed: {event.id} (customer={event.customer}, amount=${event.amount_dollars}, status={event.status})"
    )


@register_stripe_webhook("customer.updated")
@transaction.atomic
def handle_customer_updated(data: dict):
    event = StripeCustomer.model_validate(data)

    customer = _get_customer_or_none(event.id, "customer.updated")
    if not customer:
        return

    updated_fields = []

    if event.email and event.email != customer.billing_email:
        old_email = customer.billing_email
        customer.billing_email = event.email
        updated_fields.append("billing_email")

    if updated_fields:
        updated_fields.append("updated_at")
        customer.save(update_fields=updated_fields)
        log.info(f"Synced customer {customer.pk} from Stripe: updated {updated_fields}")
    else:
        log.debug(f"customer.updated for {customer.pk} — no field changes")
