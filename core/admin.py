from django.contrib import admin
from core.models import WebhookEvent, WebhookHandlerResult, ScheduledEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["stripe_event_id", "event_type", "processed", "created_at", "processed_at"]
    list_filter = ["event_type", "processed"]
    search_fields = ["stripe_event_id"]
    readonly_fields = ["stripe_event_id", "event_type", "payload", "processed", "processed_at", "created_at"]


@admin.register(WebhookHandlerResult)
class WebhookHandlerResultAdmin(admin.ModelAdmin):
    list_display = ["event", "handler_name", "processed", "processed_at"]
    list_filter = ["processed", "handler_name"]
    search_fields = ["handler_name", "event__stripe_event_id"]
    readonly_fields = ["event", "handler_name", "processed", "processed_at"]


@admin.register(ScheduledEvent)
class ScheduledEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "execute_at", "processed", "attempts"]
    list_filter = ["event_type", "processed"]
