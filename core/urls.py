from django.urls import path
from core.views import health_check, stripe_webhook

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("webhooks/stripe/", stripe_webhook, name="stripe-webhook"),
]
