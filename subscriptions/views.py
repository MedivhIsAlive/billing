from rest_framework import viewsets, generics, permissions

from django_filters.rest_framework import DjangoFilterBackend

from subscriptions.models import Subscription
from subscriptions.serializers import SubscriptionSerializer
from billing.permissions import StrictDjangoModelPermissions


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [StrictDjangoModelPermissions,]

    filter_backends = [
        DjangoFilterBackend,
    ]
    filterset_fields = {"status": ["exact", "in",]}

    def get_queryset(self):
        return Subscription.objects.select_related("plan", "user").order_by("-created_at")


class MySubscriptionView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated,]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return Subscription.objects.filter(
            user=self.request.user,
        ).select_related("plan", "user").order_by("-created_at")
