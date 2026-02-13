from rest_framework import serializers

from subscriptions.models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "customer_email",
            "stripe_subscription_id",
            "stripe_price_id",
            "status",
            "status_display",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
            "trial_start",
            "trial_end",
            "created_at",
        ]
        read_only_fields = fields
