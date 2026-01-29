from rest_framework import viewsets, generics, filters
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated

from django_filters.rest_framework import DjangoFilterBackend

from subscriptions.models import SubscriptionPlan, Subscription
from subscriptions.serializers import SubscriptionSerializer, SubscriptionPlanSerializer

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
        "is_active": ["exact"],
    }

    search_fields = ["name"]
    ordering_fields = ["price_monthly", "name", "created_at"]

    def get_queryset(self):
        return SubscriptionPlan.objects.all()


class SubscriptionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated,]

    def get_queryset(self):
        return Subscription.objects.select_related("plan").order_by("-created_at")


class MySubscriptionView(generics.ListAPIView):
    permission_classes = [IsAuthenticated,]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return Subscription.objects.filter(
            user=self.request.user,
        ).select_related("plan").order_by("-created_at")
