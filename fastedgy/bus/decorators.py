# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable

from fastedgy.dependencies import get_service
from fastedgy.bus.service import Bus, EventKey


def on_event(
    event_key: EventKey,
    priority: int = 100,
) -> Callable:
    """
    Decorator to register an event listener.

    Supports multiple decorators on the same handler for different events.

    Args:
        event_key: Event class or Token[EventClass]("custom_name")
        priority: Priority (lower = executed first, default: 100)

    Example:
        ```python
        @on_event(OnAuthRefreshTokenEvent, priority=10)
        async def _update_household_last_login_at(event: OnAuthRefreshTokenEvent) -> None:
            pass

        # Multiple decorators on same handler
        @on_event(EventA, priority=10)
        @on_event(EventB, priority=20)
        async def handle_multiple(event: Union[EventA, EventB]) -> None:
            pass

        # With Token
        CUSTOM_EVENT = Token[OnAuthRefreshTokenEvent]("auth.custom")
        @on_event(CUSTOM_EVENT, priority=5)
        async def handler(event: OnAuthRefreshTokenEvent) -> None:
            pass
        ```
    """

    def decorator(func: Callable) -> Callable:
        bus = get_service(Bus)
        bus.register(event_key, func, priority=priority)
        return func

    return decorator


__all__ = [
    "on_event",
]
