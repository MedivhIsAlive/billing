from django.urls import path

from payments.views import (
    create_checkout_session,
    create_portal_session,
    get_billing_status,
    get_purchase_history,
    get_available_products_view,
)

app_name = "payments"

urlpatterns = [
    path("checkout/", create_checkout_session, name="checkout"),
    path("portal/", create_portal_session, name="portal"),
    path("status/", get_billing_status, name="billing-status"),
    path("history/", get_purchase_history, name="purchase-history"),
    path("products/", get_available_products_view, name="products"),
]
