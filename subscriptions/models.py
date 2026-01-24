from django.db import models


ALLOW_INFINITE_SUBSCRIPTIONS = True


class Subscription(models.Model):
    class Status(models.TextChoices):
            ACTIVE = "active"
            PAUSED = "paused"
            DISABLED = "disabled"

    status = models.CharField(max_length=12, choices=Status.choices)
    current_period_end = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["status", "current_period_end"]),
        ]
