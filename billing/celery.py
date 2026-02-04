import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "billing.settings")

app = Celery("billing")
app.config_from_object("django.confg:settings", namespace="CELERY")

app.autodiscover_tasks()
