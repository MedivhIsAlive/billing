from django.db import models


class WebhookEvent(models.Model):
    stripe_event_id = models.CharField(max_length=255, unique=True, db_index=True)

    event_type = models.CharField(max_length=100)

    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "webhook_events"

    def __str__(self):
        return f"{self.event_type} - {self.stripe_event_id}"


class EventType(models.TextChoices):
    SUBSCRIPTION_REMINDER = "subscription.reminder", "Subscription Reminder"
    SUBSCRIPTION_EXPIRE = "subscription.expire", "Subscription Expire"


class ScheduledEvent(models.Model):
    event_type = models.CharField(max_length=50, choices=EventType.choices, db_index=True)

    execute_at = models.DateTimeField(db_index=True)

    payload = models.JSONField(default=dict)

    processed = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scheduled_events"
        indexes = [
            models.Index(fields=["processed", "execute_at"]),
        ]

    def __str__(self):
        status = "done" if self.processed else "pending"
        return f"{self.event_type} @ {self.execute_at} ({status})"
