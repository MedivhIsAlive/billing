from django.contrib import admin
from accounts.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["user", "billing_email", "stripe_customer_id", "created_at"]
    search_fields = ["user__email", "user__username", "billing_email", "stripe_customer_id"]
    readonly_fields = ["stripe_customer_id", "created_at", "updated_at"]
