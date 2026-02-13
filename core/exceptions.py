import logging
from rest_framework.views import exception_handler

log = logging.getLogger("billing.core.exceptions")


class WebhookError(Exception):
    def __init__(self, message: str, key: str = "", context=None, expected=True, *, retryable=None):
        self.message = message
        self.key = key
        self.context = context or {}
        self.expected = expected
        self.retryable = retryable

    def __str__(self):
        return self.message

    def __repr__(self):
        return f"{self.__class__.__name__}(key={self.key!r}, retryable={self.retryable})"


class WebhookSkip(WebhookError):
    def __init__(self, message: str, key: str = "webhook@skipped", context=None):
        super().__init__(message, key, context, expected=True, retryable=False)


class WebhookRetry(WebhookError):
    def __init__(self, message: str, key: str = "webhook@retry", context=None):
        super().__init__(message, key, context, expected=False, retryable=True)


class WebhookInfrastructureError(WebhookRetry):
    def __init__(self, message: str, context=None):
        super().__init__(message, key="webhook@infrastructure", context=context)


def drf_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None and response.status_code >= 500:
        log.exception(
            f"DRF server error in {context.get('view', 'unknown')}",
            extra={
                "view": str(context.get("view")),
                "status_code": response.status_code,
            },
        )
    elif response is not None and response.status_code >= 400:
        log.warning(f"DRF client error {response.status_code} in {context.get('view', 'unknown')}")

    return response


__all__ = (
    "WebhookError",
    "WebhookSkip",
    "WebhookRetry",
    "WebhookInfrastructureError",
    "drf_exception_handler",
)
