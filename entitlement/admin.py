from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from entitlement.models import Entitlement


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "feature",
        "granted_by",
        "status_badge",
        "usage_display",
        "expires_at",
        "created_at",
    ]
    list_filter = [
        "granted_by",
        "is_active",
        "feature",
        "created_at",
        "expires_at",
    ]
    search_fields = [
        "customer__user__email",
        "customer__user__username",
        "feature",
        "revoke_reason",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "revoked_at",
        "usage_count",
        "is_valid_status",
    ]
    raw_id_fields = ["customer"]

    fieldsets = (
        ("Customer & Feature", {
            "fields": ("customer", "feature", "granted_by")
        }),
        ("Access Control", {
            "fields": ("is_active", "expires_at", "revoked_at", "revoke_reason")
        }),
        ("Usage Tracking", {
            "fields": ("usage_limit", "usage_count")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    actions = ["revoke_selected", "activate_selected"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        # thanks to chatgpt for icons; i like them tbh
        if obj.is_valid:
            color = "green"
            text = "✓ Valid"
        elif not obj.is_active:
            color = "red"
            text = "✗ Revoked"
        elif obj.expires_at and timezone.now() > obj.expires_at:
            color = "orange"
            text = "⏱ Expired"
        elif obj.usage_limit and obj.usage_count >= obj.usage_limit:
            color = "orange"
            text = "⚠ Limit Reached"
        else:
            color = "gray"
            text = "? Unknown"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            text
        )

    @admin.display(description="Usage")
    def usage_display(self, obj):
        if obj.usage_limit:
            percentage = (obj.usage_count / obj.usage_limit) * 100
            return f"{obj.usage_count}/{obj.usage_limit} ({percentage:.0f}%)"
        return f"{obj.usage_count}/∞"

    @admin.display(description="Currently Valid")
    def is_valid_status(self, obj):
        return "✓ Yes" if obj.is_valid else "✗ No"

    @admin.action(description="Revoke selected entitlements")
    def revoke_selected(self, request, queryset):
        count = 0
        for entitlement in queryset:
            entitlement.revoke(reason="Admin revocation")
            count += 1
        self.message_user(request, f"Revoked {count} entitlement(s).")

    @admin.action(description="Activate selected entitlements")
    def activate_selected(self, request, queryset):
        count = queryset.update(is_active=True, revoked_at=None, revoke_reason="")
        self.message_user(request, f"Activated {count} entitlement(s).")
