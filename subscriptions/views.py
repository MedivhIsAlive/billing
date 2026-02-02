from rest_framework import viewsets, generics, filters, permissions, throttling

from django_filters.rest_framework import DjangoFilterBackend

from subscriptions.models import SubscriptionPlan, Subscription
from subscriptions.serializers import SubscriptionSerializer, SubscriptionPlanSerializer
from billing.permissions import StrictDjangoModelPermissions

class SubscriptionPlanView(generics.ListAPIView):
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny,]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = {
        "price_monthly": ["exact", "gte", "lte",],
    }

    search_fields = ["name"]
    ordering_fields = ["price_monthly", "name", "created_at"]
    throttle_classes = [throttling.AnonRateThrottle,]

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)


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
