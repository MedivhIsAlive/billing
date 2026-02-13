import logging

from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payments.serializers import (
    CheckoutRequestSerializer,
    CheckoutResponseSerializer,
    ErrorSerializer,
    PortalResponseSerializer,
    ProductListResponseSerializer,
    BillingStatusResponseSerializer,
    PurchaseHistoryResponseSerializer,
)
from payments.services import (
    create_checkout,
    create_portal_url,
    get_billing_status_for_user,
    get_purchase_history_for_user,
    get_available_products,
)

log = logging.getLogger("billing.payments")


@extend_schema(
    request=CheckoutRequestSerializer,
    responses={200: CheckoutResponseSerializer, 400: ErrorSerializer},
    examples=[
        OpenApiExample("Subscription", value={"price_id": "price_pro_monthly"}, request_only=True),
        OpenApiExample("One-time payment", value={"price_id": "price_setup_fee", "mode": "payment"}, request_only=True),
    ],
    tags=["Payments"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    serializer = CheckoutRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    checkout_url = create_checkout(
        user=request.user,
        price_id=data["price_id"],
        quantity=data.get("quantity", 1),
        mode=data.get("mode"),
        idempotency_key=data.get("idempotency_key"),
    )

    return Response({"checkout_url": checkout_url})


@extend_schema(responses={200: PortalResponseSerializer}, tags=["Payments"])
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_portal_session(request):
    portal_url = create_portal_url(request.user)
    return Response({"portal_url": portal_url})


@extend_schema(responses={200: BillingStatusResponseSerializer}, tags=["Payments"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_billing_status(request):
    status = get_billing_status_for_user(request.user)
    return Response(status)


@extend_schema(responses={200: PurchaseHistoryResponseSerializer}, tags=["Payments"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_purchase_history(request):
    purchases = get_purchase_history_for_user(request.user)
    return Response({"purchases": purchases})


@extend_schema(responses={200: ProductListResponseSerializer}, tags=["Payments"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_available_products_view(request):
    products = get_available_products()
    return Response({"products": products})
