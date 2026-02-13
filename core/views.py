import logging
from typing import Optional

import stripe
from celery import current_app
from django.conf import settings
from django.db import IntegrityError, connection
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.models import WebhookEvent
from core.serializers import HealthCheckResponseSerializer
from core.tasks import process_webhook_event

log = logging.getLogger("billing.core.views")


def _check_database() -> Optional[str]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return None
    except Exception as e:
        return str(e)


def _check_redis() -> Optional[str]:
    if not settings.CELERY_RESULT_BACKEND:
        return "not configured"
    try:
        from redis import Redis

        with Redis.from_url(
            settings.CELERY_RESULT_BACKEND,
            socket_connect_timeout=1,
            socket_timeout=1,
        ) as redis_client:
            redis_client.ping()
        return None
    except Exception as e:
        return str(e)


def _check_celery() -> Optional[str]:
    try:
        inspect = current_app.control.inspect(timeout=1.0)
        stats = inspect.stats()
        if not stats:
            return "no workers"
        return None
    except Exception as e:
        return str(e)


def _check_stripe() -> Optional[str]:
    if not settings.STRIPE_SECRET_KEY:
        return "not configured"
    try:
        stripe.Account.retrieve(api_key=settings.STRIPE_SECRET_KEY)
        return None
    except Exception as e:
        return str(e)


@extend_schema(
    summary="Health Check",
    description="Checks the health of all critical services.",
    responses={
        200: OpenApiResponse(
            response=HealthCheckResponseSerializer,
            description="All services are healthy",
            examples=[
                OpenApiExample(
                    "All Healthy",
                    value={
                        "status": "healthy",
                        "service_details": {"database": "ok", "celery": "ok", "redis": "ok", "stripe": "ok"},
                    },
                )
            ],
        ),
        503: OpenApiResponse(
            response=HealthCheckResponseSerializer,
            description="One or more services are down",
        ),
    },
    tags=["Health"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    checks = {
        "database": _check_database,
        "celery": _check_celery,
        "redis": _check_redis,
        "stripe": _check_stripe,
    }

    result = {}
    all_healthy = True

    for name, check_fn in checks.items():
        error = check_fn()
        if error:
            all_healthy = False
            result[name] = error
            log.error(f"Health check failed for {name}: {error}")
        else:
            result[name] = "ok"

    return Response(
        {"status": "healthy" if all_healthy else "down", "service_details": result},
        status=200 if all_healthy else 503,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    if not sig_header:
        return Response({"error": "Missing Stripe-Signature header"}, status=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        log.warning("Invalid webhook payload")
        return Response({"error": "Invalid payload"}, status=400)
    except stripe.SignatureVerificationError:
        log.warning("Invalid webhook signature")
        return Response({"error": "Invalid signature"}, status=400)

    log.info(f"Received Stripe event {event.id} ({event.type})")

    if WebhookEvent.objects.filter(stripe_event_id=event.id).exists():
        log.info(f"Duplicate event {event.id}, skipping")
        return Response(status=200)

    try:
        WebhookEvent.objects.create(
            stripe_event_id=event.id,
            event_type=event.type,
            payload=event.data.object,
        )
    except IntegrityError:
        log.info(f"Duplicate event {event.id} (race), skipping")
        return Response(status=200)

    process_webhook_event.delay(event.id)

    return Response(status=200)
