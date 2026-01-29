from django.urls import path, include
from rest_framework.routers import DefaultRouter
from subscriptions.views import SubscriptionViewSet, MySubscriptionView, SubscriptionPlanView


router = DefaultRouter()
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")


urlpatterns = [
    path("subscriptions/me/", MySubscriptionView.as_view(), name="subscriptions-me"),
    path("plans", SubscriptionPlanView.as_view(), name="subscription-plans"),
    path("", include(router.urls))
]
