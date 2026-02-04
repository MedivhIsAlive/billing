from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import health_check

urlpatterns = [
    path("health/", health_check)
]
