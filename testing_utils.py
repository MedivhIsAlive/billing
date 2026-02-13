import itertools
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Customer
from subscriptions.models import Subscription, SubscriptionStatus

User = get_user_model()

_counter = itertools.count(1)


def _next_id():
    return next(_counter)


def make_user(email=None, username=None, password="testpass123"):
    n = _next_id()
    email = email or f"test{n}@example.com"
    username = username or f"testuser{n}"
    return User.objects.create_user(username=username, email=email, password=password)


def make_customer(user=None, stripe_customer_id=None):
    n = _next_id()
    if user is None:
        user = make_user()
    stripe_customer_id = stripe_customer_id or f"cus_test{n}"
    return Customer.objects.create(user=user, stripe_customer_id=stripe_customer_id)


def make_subscription(
    customer=None,
    stripe_subscription_id=None,
    stripe_price_id="price_pro_monthly",
    status=SubscriptionStatus.ACTIVE,
    period_days=30,
    created_at=None,
):
    n = _next_id()
    if customer is None:
        customer = make_customer()
    stripe_subscription_id = stripe_subscription_id or f"sub_test{n}"
    now = timezone.now()
    return Subscription.objects.create(
        customer=customer,
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id=stripe_price_id,
        status=status,
        current_period_start=now,
        current_period_end=now + timedelta(days=period_days),
        created_at=created_at,
    )


def make_stripe_subscription_data(
    sub_id="sub_test123",
    customer_id="cus_test123",
    price_id="price_pro_monthly",
    status="active",
    period_start=None,
    period_end=None,
    cancel_at_period_end=False,
):
    now = timezone.now()
    start = int((period_start or now).timestamp())
    end = int((period_end or now + timedelta(days=30)).timestamp())

    return {
        "id": sub_id,
        "customer": customer_id,
        "status": status,
        "items": {"data": [{"price": {"id": price_id}}]},
        "current_period_start": start,
        "current_period_end": end,
        "cancel_at_period_end": cancel_at_period_end,
        "canceled_at": None,
        "trial_start": None,
        "trial_end": None,
    }


def make_stripe_invoice_data(
    invoice_id="in_test123",
    customer_id="cus_test123",
    billing_reason="subscription_create",
    lines=None,
):
    if lines is None:
        lines = [
            {
                "amount": 2999,
                "description": "Pro Monthly",
                "price": {"id": "price_pro_monthly"},
            }
        ]

    return {
        "id": invoice_id,
        "customer": customer_id,
        "billing_reason": billing_reason,
        "lines": {"data": lines},
    }


def make_stripe_charge_data(
    charge_id="ch_test123",
    invoice_id="in_test123",
    amount_refunded=2999,
):
    return {
        "id": charge_id,
        "invoice": invoice_id,
        "amount_refunded": amount_refunded,
    }


def make_stripe_checkout_session_data(
    session_id="cs_test123",
    customer_id="cus_test123",
    mode="payment",
    payment_status="paid",
    amount_total=2999,
    currency="usd",
    subscription=None,
    payment_intent="pi_test123",
    metadata=None,
):
    return {
        "id": session_id,
        "customer": customer_id,
        "mode": mode,
        "payment_status": payment_status,
        "amount_total": amount_total,
        "currency": currency,
        "subscription": subscription,
        "payment_intent": payment_intent,
        "metadata": metadata or {},
    }


def make_stripe_dispute_data(
    dispute_id="dp_test123",
    charge_id="ch_test123",
    amount=2999,
    currency="usd",
    reason="fraudulent",
    status="needs_response",
    payment_intent="pi_test123",
):
    return {
        "id": dispute_id,
        "charge": charge_id,
        "amount": amount,
        "currency": currency,
        "reason": reason,
        "status": status,
        "payment_intent": payment_intent,
    }


def make_stripe_customer_data(
    customer_id="cus_test123",
    email="updated@example.com",
    name="Test User",
):
    return {
        "id": customer_id,
        "email": email,
        "name": name,
        "metadata": {},
    }


def make_stripe_payment_intent_data(
    pi_id="pi_test123",
    customer_id="cus_test123",
    amount=2999,
    status="requires_payment_method",
    invoice=None,
):
    return {
        "id": pi_id,
        "customer": customer_id,
        "amount": amount,
        "status": status,
        "invoice": invoice,
    }
