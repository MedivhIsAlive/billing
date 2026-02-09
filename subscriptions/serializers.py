from rest_framework import serializers

from subscriptions.models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "user_email",
            "status",
            "status_display",
            "current_period_end",
            "created_at",
        ]
