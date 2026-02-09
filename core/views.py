import logging
from typing import Optional

import stripe
from celery import current_app
from django.conf import settings
from django.db import IntegrityError, connection
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from redis import Redis
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.models import WebhookEvent
from core.serializers import HealthCheckResponseSerializer
from core.stripe.event_handlers import try_dispatch_event

logger = logging.getLogger("billing")


def check_database() -> Optional[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def check_redis() -> Optional[str]:
    with Redis.from_url(
        settings.CELERY_RESULT_BACKEND,
        socket_connect_timeout=1,
        socket_timeout=1,
    ) as redis_client:
        redis_client.ping()


def check_celery() -> Optional[str]:
    inspect = current_app.control.inspect(timeout=1.0)
    stats = inspect.stats()
    if not stats:
        return "no workers"


def check_stripe() -> Optional[str]:
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.Account.retrieve(timeout=2)
        return None
    else:
        return "not configured"


# TODO: dont really like two sources of truth thing where we use serializers exclusively for openapi
@extend_schema(
    summary="Health Check",
    description="Checks the health of all critical services including database, Redis, RabbitMQ (via Celery), and Stripe API.",
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
            examples=[
                OpenApiExample(
                    "Service Down",
                    value={
                        "status": "down",
                        "service_details": {"database": "ok", "celery": "down", "redis": "ok", "stripe": "ok"},
                    },
                )
            ],
        ),
    },
    tags=["Health"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    result = {}
    all_healthy = True

    health_checks = {
        "database": check_database,
        "celery": check_celery,
        "redis": check_redis,
        "stripe": check_stripe,
    }

    for service_name, check_func in health_checks.items():
        try:
            result[service_name] = check_func() or "ok"
        except Exception as e:
            logger.error(
                f"{service_name} health check failed with error: {e}",
                exc_info=True,
            )
            all_healthy = False
            result[service_name] = "down"

    return Response(
        {"status": "healthy" if all_healthy else "down", "service_details": result},
        status=200 if all_healthy else 503,
    )


@api_view(["POST"])
@permission_classes([AllowAny,])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as e:
        logger.warning(f"Invalid signature verification failed: {e}")
        return Response(status=400)

    logger.info(f"Successfully constructed event {event.id} {event.type}")

    try:
        WebhookEvent.objects.create(
            stripe_event_id=event.id,
            event_type=event.type,
        )
    except IntegrityError:
        logger.info("Event was already processed!")
        return Response(status=200)

    try_dispatch_event(event.type, event.data.object)
    return Response(status=200)
