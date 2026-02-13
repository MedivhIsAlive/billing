import logging

import stripe
from django.conf import settings
from django.core.cache import cache

from accounts.models import Customer
from entitlement.services import get_active_entitlements
from purchases.models import Purchase
from subscriptions.models import Subscription, SubscriptionStatus
from utility.collections import filtered_dict

log = logging.getLogger("billing.payments.services")

PRODUCT_CACHE_KEY = "stripe:products_and_prices"


def get_or_create_stripe_customer(user) -> Customer:
    customer, _ = Customer.objects.get_or_create(user=user)

    if not customer.stripe_customer_id:
        stripe_customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.id)},
        )
        customer.stripe_customer_id = stripe_customer.id
        customer.save(update_fields=["stripe_customer_id"])
        log.info(f"Created Stripe customer {stripe_customer.id} for user {user.id}")

    return customer


def create_checkout(
    user, price_id: str, quantity: int = 1, mode: str | None = None, idempotency_key: str | None = None
) -> str:
    customer = get_or_create_stripe_customer(user)

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

    session = stripe.checkout.Session.create(
        **session_params, **filtered_dict({"idempotency_key": idempotency_key}),
    )
    assert session.url, "No url from session"
    return session.url


def create_portal_url(user) -> str:
    customer = get_or_create_stripe_customer(user)

    session = stripe.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=settings.STRIPE_PORTAL_RETURN_URL,
    )
    return session.url


def get_billing_status_for_user(user) -> dict:
    customer = Customer.objects.filter(user=user).first()

    if not customer:
        return {"has_subscription": False, "subscription": None, "entitlements": []}

    subscription = Subscription.objects.filter(
        customer=customer,
        status__in=[
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.PAST_DUE,
        ],
    ).first()

    entitlements = get_active_entitlements(customer)

    return {
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


def get_purchase_history_for_user(user, limit: int = 50) -> list[dict]:
    customer = Customer.objects.filter(user=user).first()

    if not customer:
        return []

    purchases = Purchase.objects.filter(customer=customer).order_by("-created_at")[:limit]

    return [
        {
            "product_name": p.product_name,
            "amount": str(p.amount),
            "status": p.status,
            "created_at": p.created_at,
        }
        for p in purchases
    ]


def get_available_products() -> list[dict]:
    cached = cache.get(PRODUCT_CACHE_KEY)
    if cached is not None:
        return cached

    products = stripe.Product.list(active=True)
    prices = stripe.Price.list(active=True)

    price_map: dict[str, list] = {}
    for price in prices.data:
        product_id = price.product if isinstance(price.product, str) else price.product.id
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

    result = [
        {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "prices": price_map.get(product.id, []),
        }
        for product in products.data
    ]

    ttl = getattr(settings, "STRIPE_PRODUCT_CACHE_TTL", 300)
    cache.set(PRODUCT_CACHE_KEY, result, timeout=ttl)
    log.info(f"Cached {len(result)} products for {ttl}s")

    return result


def invalidate_product_cache():
    cache.delete(PRODUCT_CACHE_KEY)
