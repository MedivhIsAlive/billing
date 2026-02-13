import logging
from datetime import timedelta

import stripe
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from subscriptions.models import Subscription, SubscriptionStatus

log = logging.getLogger("billing.core.stripe.tasks")

GRACE_PERIOD_DAYS = 7
REMINDER_DAYS = {7, 3, 1}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_subscription_lifecycle(self):
    today = timezone.now().date()
    reminded = 0
    expired = 0

    active_subs = Subscription.objects.filter(
        status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
        cancel_at_period_end=True,
    ).select_related("customer", "customer__user")

    for sub in active_subs:
        days_until_end = (sub.current_period_end.date() - today).days

        if days_until_end in REMINDER_DAYS:
            _send_reminder(sub, days_until_end)
            reminded += 1

    grace_cutoff = timezone.now() - timedelta(days=GRACE_PERIOD_DAYS)
    past_due_subs = Subscription.objects.filter(
        status=SubscriptionStatus.PAST_DUE,
        current_period_end__lt=grace_cutoff,
    ).select_related("customer", "customer__user")

    for sub in past_due_subs:
        _expire_subscription(sub)
        expired += 1

    log.info(f"Subscription lifecycle: sent {reminded} reminders, expired {expired} subscriptions")


def _send_reminder(subscription: Subscription, days: int):
    customer = subscription.customer
    email = customer.email

    if not email:
        log.warning(f"No email for customer {customer.pk}, skipping reminder")
        return

    subject = f"Your subscription ends in {days} day{'s' if days != 1 else ''}"
    message = (
        f"Hi,\n\n"
        f"Your subscription ({subscription.stripe_price_id}) is set to end "
        f"on {subscription.current_period_end.strftime('%B %d, %Y')}.\n\n"
        f"If you'd like to continue your subscription, you can update your "
        f"billing settings before it expires.\n\n"
        f"Thanks for being a customer!"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[email],
            fail_silently=False,
        )
        log.info(f"Sent {days}-day reminder to {email} for subscription {subscription.pk}")

    except Exception as e:
        log.error(f"Failed to send reminder to {email} for subscription {subscription.pk}: {e}")


def _expire_subscription(subscription: Subscription):
    from entitlement.services import revoke_for_subscription

    log.info(f"Expiring subscription {subscription.pk} for customer {subscription.customer_id} (past grace period)")

    subscription.cancel()
    revoke_for_subscription(subscription, reason="Past-due subscription expired after grace period")


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def sync_stale_subscriptions_from_stripe(self):
    if not settings.STRIPE_SECRET_KEY:
        log.warning("Stripe not configured, skipping subscription sync")
        return

    stale_cutoff = timezone.now() - timedelta(hours=48)
    stale_subs = Subscription.objects.filter(
        status__in=[
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.PAST_DUE,
        ],
        updated_at__lt=stale_cutoff,
    ).select_related("customer")

    synced = 0
    for sub in stale_subs:
        try:
            stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
            sub.status = stripe_sub.status
            sub.cancel_at_period_end = stripe_sub.cancel_at_period_end
            sub.save(update_fields=["status", "cancel_at_period_end", "updated_at"])
            synced += 1
        except stripe.StripeError as e:
            log.error(f"Failed to sync subscription {sub.stripe_subscription_id} from Stripe: {e}")

    log.info(f"Synced {synced} stale subscriptions from Stripe")
