from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

# Versioned API routes
v1_patterns = [
    path("subscriptions/", include("subscriptions.urls")),
    path("payments/", include("payments.urls")),
    path("", include("core.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # Versioned endpoints
    path("api/v1/", include((v1_patterns, "v1"))),

    # Backwards-compatible unversioned routes (alias to v1)
    path("api/subscriptions/", include("subscriptions.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/", include("core.urls")),
]
