from collections import defaultdict
from typing import Callable, Dict, List


HANDLERS: Dict[str, List[Callable]] = defaultdict(list)


def register_stripe_webhook(event_type: str):
    def decorator(fn: Callable) -> Callable:
        HANDLERS[event_type].append(fn)
        return fn

    return decorator


def try_dispatch_event(event_type: str, data: dict) -> int:
    """
    Returns:
        int - amount of handlers that processed this event
    """
    handlers = get_handlers(event_type)
    for handler in handlers:
        handler(data)
    return len(handlers)


def get_handlers(event_type: str) -> List[Callable]:
    return HANDLERS.get(event_type, [])
