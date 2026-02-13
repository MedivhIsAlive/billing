from rest_framework import serializers


class CheckoutRequestSerializer(serializers.Serializer):
    price_id = serializers.CharField()
    quantity = serializers.IntegerField(default=1, required=False)
    mode = serializers.ChoiceField(choices=["subscription", "payment"], required=False)
    idempotency_key = serializers.CharField(required=False)


class CheckoutResponseSerializer(serializers.Serializer):
    checkout_url = serializers.URLField()


class PortalResponseSerializer(serializers.Serializer):
    portal_url = serializers.URLField()


class SubscriptionSerializer(serializers.Serializer):
    status = serializers.CharField()
    price_id = serializers.CharField()
    current_period_end = serializers.DateTimeField()
    cancel_at_period_end = serializers.BooleanField()


class BillingStatusResponseSerializer(serializers.Serializer):
    has_subscription = serializers.BooleanField()
    subscription = SubscriptionSerializer(allow_null=True)
    entitlements = serializers.ListField(child=serializers.CharField())


class PurchaseSerializer(serializers.Serializer):
    product_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class PurchaseHistoryResponseSerializer(serializers.Serializer):
    purchases = PurchaseSerializer(many=True)


class PriceSerializer(serializers.Serializer):
    id = serializers.CharField()
    amount = serializers.IntegerField()
    currency = serializers.CharField()
    interval = serializers.CharField(allow_null=True)


class ProductSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    prices = PriceSerializer(many=True)


class ProductListResponseSerializer(serializers.Serializer):
    products = ProductSerializer(many=True)


class ErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
