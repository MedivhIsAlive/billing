import logging

from accounts.models import Customer
from core.stripe.event_handler import WebhookHandler
from core.stripe.models import StripeCustomer

log = logging.getLogger("billing.accounts.stripe_handlers")


class HandleCustomerUpdated(WebhookHandler):
    __event__ = "customer.updated"

    @classmethod
    def handle(cls, data: dict):
        event = StripeCustomer.model_validate(data)

        try:
            customer = Customer.objects.get(stripe_customer_id=event.id)
        except Customer.DoesNotExist:
            log.warning(f"No customer for stripe_customer_id={event.id} (customer.updated)")
            return

        updated_fields = []

        if event.email and event.email != customer.billing_email:
            customer.billing_email = event.email
            updated_fields.append("billing_email")

        if updated_fields:
            updated_fields.append("updated_at")
            customer.save(update_fields=updated_fields)
            log.info(f"Synced customer {customer.pk} from Stripe: updated {updated_fields}")
        else:
            log.debug(f"customer.updated for {customer.pk} — no field changes")


__all__ = ("HandleCustomerUpdated",)
