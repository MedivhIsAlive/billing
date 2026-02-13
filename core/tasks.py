import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from core.exceptions import WebhookSkip
from core.models import WebhookEvent, ScheduledEvent
from core.stripe.event_handler import dispatch_event, dispatch_tracked_event

log = logging.getLogger("billing.core.tasks")


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def process_webhook_event(self, stripe_event_id: str):
    try:
        event = WebhookEvent.objects.get(stripe_event_id=stripe_event_id)
    except WebhookEvent.DoesNotExist:
        log.error(f"WebhookEvent {stripe_event_id} not found, cannot process")
        return

    if event.processed:
        log.debug(f"Event {stripe_event_id} already fully processed")
        return

    try:
        dispatch_tracked_event(event, event.event_type, event.payload)

        event.processed = True
        event.processed_at = timezone.now()
        event.save(update_fields=["processed", "processed_at"])

        log.info(f"Event {stripe_event_id} fully processed")

    except WebhookSkip as e:
        log.info(f"Skipped event {stripe_event_id}: {e}")
        event.processed = True
        event.processed_at = timezone.now()
        event.save(update_fields=["processed", "processed_at"])

    except Exception as exc:
        log.warning(
            f"Error processing event {stripe_event_id} "
            f"(attempt {self.request.retries + 1}/{self.max_retries + 1}): {exc}"
        )
        raise self.retry(exc=exc)


@shared_task
def cleanup_webhook_events():
    cutoff = timezone.now() - timedelta(days=90)
    count, _ = WebhookEvent.objects.filter(created_at__lt=cutoff).delete()
    log.info(f"Cleaned up {count} old webhook events")


@shared_task(max_retries=3, default_retry_delay=30)
def process_scheduled_events():
    now = timezone.now()
    max_attempts = getattr(settings, "SCHEDULED_EVENT_MAX_ATTEMPTS", 5)
    processed_count = 0
    failed_events = []
    is_postgres = getattr(settings, "IS_POSTGRES", False)

    with transaction.atomic():
        qs = ScheduledEvent.objects.filter(
            processed=False,
            execute_at__lte=now,
            attempts__lt=max_attempts,
        ).order_by("execute_at")

        if is_postgres:
            qs = qs.select_for_update(skip_locked=True)
        else:
            qs = qs.select_for_update()

        pending = list(qs[:100])

        for event in pending:
            try:
                dispatch_event(event.event_type, event.payload)
                event.processed = True
                event.processed_at = now
                event.attempts += 1
                event.save(update_fields=["processed", "processed_at", "attempts"])
                processed_count += 1
            except Exception as e:
                failed_events.append((event, e))

    for event, error in failed_events:
        ScheduledEvent.objects.filter(pk=event.pk, processed=False).update(
            attempts=models.F("attempts") + 1,
            last_error=str(error)[:500],
        )
        log.error(f"Failed scheduled event {event.pk} (attempt {event.attempts + 1}/{max_attempts}): {error}")

    if processed_count:
        log.info(f"Processed {processed_count} scheduled events")
