import logging

from accounts.models import Customer
from core.exceptions import WebhookSkip
from core.stripe.event_handler import WebhookHandler
from core.stripe.models import (
    StripeInvoice,
    StripeCharge,
    StripeCheckoutSession,
    StripeDispute,
    StripePaymentIntent,
)
from purchases.models import Purchase, PurchaseType

log = logging.getLogger("billing.purchases.stripe_handlers")


def _get_customer_or_skip(stripe_customer_id: str, context: str) -> Customer:
    try:
        return Customer.objects.get(stripe_customer_id=stripe_customer_id)
    except Customer.DoesNotExist:
        raise WebhookSkip(
            f"No customer for stripe_customer_id={stripe_customer_id} ({context})",
            context={"stripe_customer_id": stripe_customer_id},
        )


def _get_customer_or_none(stripe_customer_id: str, context: str) -> Customer | None:
    try:
        return Customer.objects.get(stripe_customer_id=stripe_customer_id)
    except Customer.DoesNotExist:
        log.warning(f"No customer for stripe_customer_id={stripe_customer_id} ({context})")
        return None


class HandleInvoicePaid(WebhookHandler):
    __event__ = "invoice.paid"

    @classmethod
    def handle(cls, data: dict):
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
            Purchase.objects.update_or_create(
                stripe_invoice_id=event.id,
                stripe_price_id=line.price_id,
                defaults={
                    "customer": customer,
                    "purchase_type": purchase_type,
                    "amount": line.amount_dollars,
                    "product_name": line.description,
                },
            )


class HandleCheckoutSessionCompleted(WebhookHandler):
    __event__ = "checkout.session.completed"

    @classmethod
    def handle(cls, data: dict):
        event = StripeCheckoutSession.model_validate(data)

        if event.mode != "payment":
            log.info(f"Checkout session {event.id} (mode={event.mode}), handled by subscription webhooks")
            return

        if event.payment_status != "paid":
            log.info(f"Checkout session {event.id} not yet paid (status={event.payment_status}), skipping")
            return

        if not event.customer:
            raise WebhookSkip(
                f"Checkout session {event.id} has no customer",
                context={"session_id": event.id},
            )

        customer = _get_customer_or_skip(event.customer, f"checkout.session.completed {event.id}")

        if Purchase.objects.filter(stripe_checkout_session_id=event.id).exists():
            log.info(f"Purchase already exists for checkout session {event.id}, skipping")
            return

        Purchase.objects.create(
            customer=customer,
            purchase_type=PurchaseType.ONE_TIME,
            amount=event.amount_total_dollars or 0,
            product_name=event.metadata.get("product_name", "One-time purchase"),
            stripe_checkout_session_id=event.id,
            stripe_payment_intent_id=event.payment_intent or "",
        )

        log.info(f"Created one-time purchase from checkout {event.id} for customer {customer.pk}")


class HandleChargeRefunded(WebhookHandler):
    __event__ = "charge.refunded"

    @classmethod
    def handle(cls, data: dict):
        event = StripeCharge.model_validate(data)

        if not event.invoice:
            log.info(f"Charge {event.id} refunded but has no invoice, skipping")
            return

        purchases = Purchase.objects.filter(stripe_invoice_id=event.invoice)

        if not purchases.exists():
            raise WebhookSkip(
                f"No purchase for invoice {event.invoice} on refund",
                context={"invoice_id": event.invoice},
            )

        for purchase in purchases:
            purchase.refund(event.amount_refunded_dollars)


class HandleChargeDisputeCreated(WebhookHandler):
    __event__ = "charge.dispute.created"

    @classmethod
    def handle(cls, data: dict):
        event = StripeDispute.model_validate(data)

        purchase = None

        if event.charge:
            purchase = Purchase.objects.filter(stripe_charge_id=event.charge).first()

        if not purchase and event.payment_intent:
            purchase = Purchase.objects.filter(stripe_payment_intent_id=event.payment_intent).first()

        if not purchase:
            raise WebhookSkip(
                f"No purchase for dispute {event.id} (charge={event.charge}, pi={event.payment_intent})",
                context={"dispute_id": event.id, "charge": event.charge},
            )

        purchase.mark_disputed(reason=event.reason)
        log.warning(
            f"Purchase {purchase.pk} disputed: dispute={event.id}, "
            f"reason={event.reason}, amount=${event.amount_dollars}"
        )


class HandlePaymentIntentFailed(WebhookHandler):
    __event__ = "payment_intent.payment_failed"
    __atomic__ = False

    @classmethod
    def handle(cls, data: dict):
        event = StripePaymentIntent.model_validate(data)
        log.warning(
            f"PaymentIntent failed: {event.id} "
            f"(customer={event.customer}, amount=${event.amount_dollars}, status={event.status})"
        )


__all__ = (
    "HandleInvoicePaid",
    "HandleCheckoutSessionCompleted",
    "HandleChargeRefunded",
    "HandleChargeDisputeCreated",
    "HandlePaymentIntentFailed",
)
