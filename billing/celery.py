import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "billing.settings")

app = Celery("billing")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

app.conf.beat_schedule = {
    "process-subscription-lifecycle": {
        "task": "core.stripe.tasks.process_subscription_lifecycle",
        "schedule": crontab(hour="*/4", minute="0"),
    },
    "cleanup-old-webhook-events": {
        "task": "core.tasks.cleanup_webhook_events",
        "schedule": crontab(hour="3", minute="0"),
    },
    "process-scheduled-events": {
        "task": "core.tasks.process_scheduled_events",
        "schedule": crontab(minute="*/5"),
    },
    "sync-stale-subscriptions": {
        "task": "core.stripe.tasks.sync_stale_subscriptions_from_stripe",
        "schedule": crontab(hour="2", minute="30"),
    },
}
