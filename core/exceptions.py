import logging
from rest_framework.views import exception_handler


logger = logging.getLogger("drf.exceptions")


def drf_exception_handler(exc, context):
    response = exception_handler(exc, context)

    logger.exception(
        "DRF exception",
        extra={
            "view": str(context.get("view")),
            "request": str(context.get("request")),
        },
    )

    return response

