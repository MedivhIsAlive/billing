from django.urls import path, include
from rest_framework.routers import DefaultRouter
from subscriptions.views import SubscriptionViewSet, MySubscriptionView, SubscriptionPlanView


app_name = "subscriptions"
router = DefaultRouter()
router.include_root_view = False
router.register(r"", SubscriptionViewSet, basename="subscription")


urlpatterns = [
    path("me/", MySubscriptionView.as_view(), name="me"),
    path("plans", SubscriptionPlanView.as_view(), name="plans"),
    path("", include(router.urls))
]
