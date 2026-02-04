from rest_framework import serializers

from subscriptions.models import Subscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price_monthly = serializers.DecimalField(
        max_digits=19,
        decimal_places=2,
        coerce_to_string=True,
    )

    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "price_monthly"]


class SubscriptionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    plan = serializers.SlugRelatedField(
        slug_field="name",
        queryset=SubscriptionPlan.objects.all(),
    )

    class Meta:
        model = Subscription
        fields = [
            "id",
            "user_email",
            "plan",
            "status",
            "status_display",
            "current_period_end",
            "created_at",
        ]
