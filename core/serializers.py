from rest_framework import serializers


class ServiceDetailSerializer(serializers.Serializer):
    database = serializers.CharField()
    celery = serializers.CharField()
    redis = serializers.CharField()
    stripe = serializers.CharField()


class HealthCheckResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["healthy", "down"])
    service_details = ServiceDetailSerializer()
