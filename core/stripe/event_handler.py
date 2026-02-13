import logging
from collections import defaultdict
from typing import Dict, List, Type

from core.models import WebhookHandlerResult

from django.db import transaction
from django.utils import timezone

log = logging.getLogger("billing.core.stripe.event_handler")


class WebhookHandler:
    """
    Base class for all event handlers.

    Subclasses declare __event__ to register for a event type.
    The registry lives on this class (WebhookHandler.__handlers__),

    __atomic__ controls whether handle() is wrapped in transaction.atomic.
    Defaults to True — set to False for handlers that only log.
    """

    __event__: str | None = None
    __atomic__: bool = True
    __handlers__: Dict[str, List[Type["WebhookHandler"]]] = defaultdict(list)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__event__ is not None:
            cls.__handlers__[cls.__event__].append(cls)
            log.debug(f"Registered {cls.__qualname__} for {cls.__event__}")

    @classmethod
    def handle(cls, data: dict):
        raise NotImplementedError(f"{cls.__qualname__} must implement handle()")

    @classmethod
    def handlers_for(cls, event_type: str) -> List[Type["WebhookHandler"]]:
        return list(cls.__handlers__.get(event_type, []))

    @classmethod
    def dispatch(cls, event_type: str, data: dict) -> int:
        handlers = cls.handlers_for(event_type)

        if not handlers:
            log.warning(f"No handlers registered for {event_type}")
            return 0

        for handler in handlers:
            log.info(f"Dispatching {event_type} -> {handler.__qualname__}")
            if handler.__atomic__:
                with transaction.atomic():
                    handler.handle(data)
            else:
                handler.handle(data)

        return len(handlers)

    @classmethod
    def dispatch_tracked(cls, event_record, event_type: str, data: dict) -> int:
        handlers = cls.handlers_for(event_type)

        if not handlers:
            log.warning(f"No handlers registered for {event_type}")
            return 0

        for handler in handlers:
            name = handler.__qualname__

            result, _ = WebhookHandlerResult.objects.get_or_create(
                event=event_record,
                handler_name=name,
            )

            if result.processed:
                log.debug(f"Handler {name} already processed for {event_record}, skipping")
                continue

            log.info(f"Dispatching {event_type} -> {name}")

            if handler.__atomic__:
                with transaction.atomic():
                    handler.handle(data)
            else:
                handler.handle(data)

            WebhookHandlerResult.objects.filter(
                event=event_record,
                handler_name=name,
            ).update(processed=True, processed_at=timezone.now())

        return len(handlers)

    def __repr__(self):
        return f"{self.__class__.__name__}(event={self.__event__!r})"


def dispatch_event(event_type: str, data: dict) -> int:
    return WebhookHandler.dispatch(event_type, data)

def dispatch_tracked_event(event_record, event_type: str, data: dict) -> int:
    return WebhookHandler.dispatch_tracked(event_record, event_type, data)


__all__ = (
    "WebhookHandler",
    "dispatch_event",
    "dispatch_tracked_event",
)
