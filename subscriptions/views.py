from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets, generics, permissions

from django_filters.rest_framework import DjangoFilterBackend

from subscriptions.models import Subscription
from subscriptions.serializers import SubscriptionSerializer
from billing.permissions import StrictDjangoModelPermissions


@extend_schema_view(
    list=extend_schema(summary="List all subscriptions", tags=["Subscriptions"]),
    retrieve=extend_schema(summary="Retrieve a subscription", tags=["Subscriptions"]),
)
class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [StrictDjangoModelPermissions,]

    filter_backends = [DjangoFilterBackend,]
    filterset_fields = {"status": ["exact", "in"]}

    def get_queryset(self):
        return Subscription.objects.select_related("customer", "customer__user").order_by("-created_at")


@extend_schema(
    summary="My subscriptions",
    description="Returns the authenticated user's subscriptions.",
    tags=["Subscriptions"],
)
class MySubscriptionView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return (
            Subscription.objects.filter(customer__user=self.request.user)
            .select_related("customer", "customer__user")
            .order_by("-created_at")
        )
