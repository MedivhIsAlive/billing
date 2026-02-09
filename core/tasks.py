from datetime import timedelta
from celery import shared_task
from django.utils import timezone

from core.models import WebhookEvent


@shared_task
def cleanup_webhook_events():
    cutoff = timezone.now() - timedelta(days=7)
    WebhookEvent.objects.filter(processed_at__lt=cutoff).delete()
