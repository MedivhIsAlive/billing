"""
Celery Tasks - Subscription Lifecycle

Polling approach: runs daily, checks current state, acts accordingly.
Simple, reliable, no orphaned tasks.
"""

from datetime import timedelta
from celery import shared_task
from django.utils import timezone


GRACE_PERIOD_DAYS = 7
REMINDER_DAYS = {7, 3, 1}


@shared_task
def process_subscription_reminders():
    from subscriptions.models import Subscription, SubscriptionStatus

    today = timezone.now().date()


def _send_reminder(subscription, days: int):
    ...


def _expire_subscription(subscription):
    ...
