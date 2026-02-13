from django.contrib import admin
from purchases.models import Purchase


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "product_name",
        "purchase_type",
        "amount",
        "amount_refunded",
        "status",
        "created_at",
    ]
    list_filter = ["status", "purchase_type", "created_at"]
    search_fields = [
        "customer__user__email",
        "product_name",
        "stripe_invoice_id",
        "stripe_price_id",
    ]
    readonly_fields = ["stripe_invoice_id", "stripe_price_id", "created_at"]
    raw_id_fields = ["customer"]
    ordering = ["-created_at"]
