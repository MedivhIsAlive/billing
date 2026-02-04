import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "billing.settings")

app = Celery("billing")
app.config_from_object("django.conf:settings", namespace="CELERY")


app.autodiscover_tasks()
app.conf.beat_schedule = {
    "run-daily-billing": {
        # TODO: ensure currect task
        "task": "payment.tasks.run_daily_billing",
        "schedule": crontab(hour="0", minute="0"),
    }
}
