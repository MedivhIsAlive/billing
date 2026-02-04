import logging
from typing import Optional

import stripe
from celery import current_app
from django.conf import settings
from django.db import connection
from redis import Redis
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger("billing")


# IDEA for this functions is to use them interchangeably
# so they all accept 0 args and return string if some info for checks
def check_database() -> Optional[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def check_redis() -> Optional[str]:
    with Redis.from_url(settings.CELERY_RESULT_BACKEND) as redis_client:
        redis_client.ping()


def check_celery() -> Optional[str]:
    inspect = current_app.control.inspect(timeout=1.0)
    stats = inspect.stats()
    if not stats:
        return "no workers"


def check_stripe() -> Optional[str]:
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.Account.retrieve()
        return None
    else:
        return "not configured"


# TODO: maybe add another endpoint for admin users to see errors
# TODO: maybe even remove all services info and just return status? cause security? idk
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint for monitoring.
    Checks:
    - Database connectivity
    - Redis connectivity
    - RabbitMQ (via Celery)
    - Stripe API
    """
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
