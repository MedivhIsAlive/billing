import stripe
from django.conf import settings
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

from accounts.models import Customer


stripe.api_key = settings.STRIPE_SECRET_KEY


@extend_schema(
    request=CheckoutRequestSerializer,
    responses={
        200: CheckoutResponseSerializer,
        400: ErrorSerializer,
    },
    examples=[
        OpenApiExample(
            "Subscription",
            value={"price_id": "price_pro_monthly"},
            request_only=True,
        ),
        OpenApiExample(
            "One-time payment",
            value={"price_id": "price_setup_fee", "mode": "payment"},
            request_only=True,
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    """
    Create Stripe Checkout session.

    Supports both subscriptions and one-time payments.
    Redirects user to Stripe hosted checkout page.
    """
    serializer = CheckoutRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    price_id = data["price_id"]
    quantity = data.get("quantity", 1)
    mode = data.get("mode")
    idempotency_key = data.get("idempotency_key")

    customer = get_or_create_stripe_customer(request.user)

    if not mode:
        price = stripe.Price.retrieve(price_id)
        mode = "subscription" if price.recurring else "payment"

    session_params = {
        "customer": customer.stripe_customer_id,
        "mode": mode,
        "line_items": [{"price": price_id, "quantity": quantity}],
        "success_url": settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": settings.STRIPE_CANCEL_URL,
    }

    if mode == "payment":
        session_params["invoice_creation"] = {"enabled": True}

    if idempotency_key:
        session = stripe.checkout.Session.create(**session_params, idempotency_key=idempotency_key)
    else:
        session = stripe.checkout.Session.create(**session_params)

    return Response({"checkout_url": session.url})


@extend_schema(
    responses={200: PortalResponseSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_portal_session(request):
    """
    Create Stripe Customer Portal session.

    User can manage payment methods, view invoices, cancel subscription.
    """
    customer = get_or_create_stripe_customer(request.user)

    session = stripe.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=settings.STRIPE_PORTAL_RETURN_URL,
    )

    return Response({"portal_url": session.url})


@extend_schema(
    responses={200: BillingStatusResponseSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_billing_status(request):
    """
    Get current billing status.

    Returns subscription status and active entitlements.
    """
    from subscriptions.models import Subscription, SubscriptionStatus
    from entitlement.models import Entitlement

    customer = Customer.objects.filter(user=request.user).first()

    if not customer:
        return Response({"has_subscription": False, "subscription": None, "entitlements": []})

    subscription = Subscription.objects.filter(
        customer=customer,
        status__in=[
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.PAST_DUE,
        ],
    ).first()

    entitlements = list(
        Entitlement.objects.filter(customer=customer, is_active=True).values_list("feature", flat=True).distinct()
    )

    return Response(
        {
            "has_subscription": subscription is not None,
            "subscription": {
                "status": subscription.status,
                "price_id": subscription.stripe_price_id,
                "current_period_end": subscription.current_period_end,
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
            if subscription
            else None,
            "entitlements": entitlements,
        }
    )


@extend_schema(
    responses={200: PurchaseHistoryResponseSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_purchase_history(request):
    """
    Get purchase history.
    """
    from purchases.models import Purchase

    customer = Customer.objects.filter(user=request.user).first()

    if not customer:
        return Response({"purchases": []})

    purchases = Purchase.objects.filter(customer=customer).order_by("-created_at")[:50]

    return Response(
        {
            "purchases": [
                {
                    "product_name": p.product_name,
                    "amount": str(p.amount),
                    "status": p.status,
                    "created_at": p.created_at,
                }
                for p in purchases
            ]
        }
    )


@extend_schema(
    responses={200: ProductListResponseSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_available_products(request):
    """
    Get available products and prices from Stripe.
    """
    products = stripe.Product.list(active=True)
    prices = stripe.Price.list(active=True)

    price_map = {}
    for price in prices.data:
        product_id = price.product
        if product_id not in price_map:
            price_map[product_id] = []
        price_map[product_id].append(
            {
                "id": price.id,
                "amount": price.unit_amount,
                "currency": price.currency,
                "interval": price.recurring.interval if price.recurring else None,
            }
        )

    return Response(
        {
            "products": [
                {
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "prices": price_map.get(product.id, []),
                }
                for product in products.data
            ]
        }
    )


def get_or_create_stripe_customer(user) -> Customer:
    customer, _ = Customer.objects.get_or_create(user=user)

    if not customer.stripe_customer_id:
        stripe_customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
        customer.stripe_customer_id = stripe_customer.id
        customer.save()

    return customer
