from django.contrib import admin
from subscriptions.models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "stripe_subscription_id",
        "stripe_price_id",
        "status",
        "current_period_end",
        "cancel_at_period_end",
        "created_at",
    ]
    list_filter = ["status", "cancel_at_period_end", "created_at"]
    search_fields = [
        "stripe_subscription_id",
        "stripe_price_id",
        "customer__user__email",
        "customer__user__username",
    ]
    readonly_fields = ["stripe_subscription_id", "created_at", "updated_at"]
    raw_id_fields = ["customer"]
    ordering = ["-created_at"]
