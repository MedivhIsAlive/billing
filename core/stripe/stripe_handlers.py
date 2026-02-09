import logging
from accounts.models import Customer
from core.stripe.event_handlers import register_stripe_webhook
from subscriptions.models import Subscription, SubscriptionStatus
# from entitlement.services import EntitlementService

from core.stripe.models import StripeSubscription, StripeInvoice, StripeCharge


logger = logging.getLogger("billing")


PRICE_TO_FEATURES = {
    "price_pro_monthly": ["pro", "api_access", "priority_support"],
    "price_pro_yearly": ["pro", "api_access", "priority_support"],
    "price_basic_monthly": ["basic"],
    "price_basic_yearly": ["basic"],
}


def get_features_for_price(price_id: str) -> list[str]:
    return PRICE_TO_FEATURES.get(price_id, [])


@register_stripe_webhook("customer.subscription.created")
def handle_subscription_created(data: dict):
    try:
        event = StripeSubscription.model_validate(data)
        customer = Customer.objects.get(stripe_customer_id=event.customer)
    except Exception as e:
        logger.error(f"{e}")
        raise

    logger.info("Trying to create subscription object")
    subscription = Subscription.objects.create(
        customer=customer,
        stripe_subscription_id=event.id,
        stripe_price_id=event.price_id,
        status=event.status,
        current_period_start=event.current_period_start_dt,
        current_period_end=event.current_period_end_dt,
        cancel_at_period_end=event.cancel_at_period_end,
        trial_start=event.trial_start_dt,
        trial_end=event.trial_end_dt,
    )
    logger.info(f"Successfully creeated {subscription}")

    if subscription.is_active:
        features = get_features_for_price(event.price_id)
        # EntitlementService.sync_from_subscription(subscription, features)


@register_stripe_webhook("customer.subscription.updated")
def handle_subscription_updated(data: dict):
    event = StripeSubscription.model_validate(data)

    try:
        subscription = Subscription.objects.get(stripe_subscription_id=event.id)
    except Subscription.DoesNotExist:
        return

    subscription.stripe_price_id = event.price_id
    subscription.status = event.status
    subscription.current_period_start = event.current_period_start_dt
    subscription.current_period_end = event.current_period_end_dt
    subscription.cancel_at_period_end = event.cancel_at_period_end
    subscription.canceled_at = event.canceled_at_dt
    subscription.trial_start = event.trial_start_dt
    subscription.trial_end = event.trial_end_dt
    subscription.save()

    if subscription.is_active:
        features = get_features_for_price(event.price_id)
    #     EntitlementService.sync_from_subscription(subscription, features)
    # else:
    #     EntitlementService.revoke_for_subscription(
    #         subscription,
    #         reason=f"Subscription status: {subscription.status}"
    #     )


@register_stripe_webhook("customer.subscription.deleted")
def handle_subscription_deleted(data: dict):
    event = StripeSubscription.model_validate(data)

    try:
        subscription = Subscription.objects.get(stripe_subscription_id=event.id)
    except Subscription.DoesNotExist:
        return

    subscription.status = SubscriptionStatus.CANCELED
    subscription.canceled_at = event.canceled_at_dt
    subscription.save()

    # EntitlementService.revoke_for_subscription(subscription, reason="Subscription canceled")


def handle_invoice_paid(data: dict):
    from purchases.models import Purchase, PurchaseType

    event = StripeInvoice.model_validate(data)

    try:
        customer = Customer.objects.get(stripe_customer_id=event.customer)
    except Customer.DoesNotExist:
        return

    purchase_type_map = {
        "subscription_create": PurchaseType.SUBSCRIPTION_NEW,
        "subscription_cycle": PurchaseType.SUBSCRIPTION_RENEWAL,
        "subscription_update": PurchaseType.SUBSCRIPTION_UPGRADE,
    }
    purchase_type = purchase_type_map.get(event.billing_reason or "", PurchaseType.ONE_TIME)

    for line in event.lines.data:
        Purchase.objects.create(
            customer=customer,
            purchase_type=purchase_type,
            amount=line.amount_dollars,
            product_name=line.description,
            stripe_price_id=line.price_id,
            stripe_invoice_id=event.id,
        )


def handle_invoice_payment_failed(data: dict):
    # Optional: send notification, log, etc.
    pass


def handle_charge_refunded(data: dict):
    from purchases.models import Purchase

    event = StripeCharge.model_validate(data)

    if not event.invoice:
        return

    try:
        purchase = Purchase.objects.get(stripe_invoice_id=event.invoice)
    except Purchase.DoesNotExist:
        return

    purchase.refund(event.amount_refunded_dollars)
