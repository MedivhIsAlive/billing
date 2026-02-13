import logging
from collections import defaultdict
from typing import Callable, Dict, List

log = logging.getLogger()

HANDLERS: Dict[str, List[Callable]] = defaultdict(list)


def register_stripe_webhook(event_type: str):
    def decorator(fn: Callable) -> Callable:
        HANDLERS[event_type].append(fn)
        log.debug(f"Registered handler {fn.__qualname__} for {event_type}")
        return fn

    return decorator


def try_dispatch_event(event_type: str, data: dict) -> int:
    handlers = get_handlers(event_type)

    if not handlers:
        log.warning(f"No handlers registered for event type: {event_type}")
        return 0

    for handler in handlers:
        log.info(f"Dispatching {event_type} to {handler.__qualname__}")
        handler(data)

    return len(handlers)


def get_handlers(event_type: str) -> List[Callable]:
    return HANDLERS.get(event_type, [])
