from django.contrib import admin
from core.models import WebhookEvent, ScheduledEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["stripe_event_id", "event_type", "processed_at"]
    list_filter = ["event_type", "processed_at"]
    search_fields = ["stripe_event_id", "event_type"]
    readonly_fields = ["stripe_event_id", "event_type", "processed_at"]
    ordering = ["-processed_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ScheduledEvent)
class ScheduledEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "execute_at", "processed", "attempts", "created_at"]
    list_filter = ["event_type", "processed", "execute_at"]
    search_fields = ["event_type", "last_error"]
    readonly_fields = ["created_at", "processed_at", "attempts", "last_error"]
    ordering = ["-created_at"]

    fieldsets = (
        ("Event Info", {
            "fields": ("event_type", "execute_at", "payload")
        }),
        ("Processing Status", {
            "fields": ("processed", "processed_at", "attempts", "last_error")
        }),
        ("Metadata", {
            "fields": ("created_at",)
        }),
    )
