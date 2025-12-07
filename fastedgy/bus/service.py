# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import inspect
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    TYPE_CHECKING,
)

from fastedgy.dependencies import Token
from fastedgy.bus.base import BaseEvent

if TYPE_CHECKING:
    from fastedgy.dependencies import Token as TokenType

logger = logging.getLogger("fastedgy.events")


EventKey = Union[Type[BaseEvent], "TokenType[BaseEvent]"]


class Bus:
    """Event bus for dispatching typed events with priority-based listeners"""

    def __init__(self):
        self._listeners: Dict[Token, List[Tuple[int, Callable]]] = {}

    def register(
        self,
        event_key: EventKey,
        handler: Callable,
        priority: int = 100,
    ) -> None:
        """
        Register an event listener.

        Args:
            event_key: Event class or Token[EventClass]("custom_name")
            handler: Callable that accepts an event instance
            priority: Priority (lower = executed first, default: 100)
        """
        normalized_key = self._normalize_key(event_key)

        if normalized_key not in self._listeners:
            self._listeners[normalized_key] = []

        self._listeners[normalized_key].append((priority, handler))
        self._listeners[normalized_key].sort(key=lambda x: x[0])

        logger.debug(
            f"Registered listener for {normalized_key} with priority {priority}: {handler.__name__}"
        )

    async def dispatch(
        self, event: BaseEvent, event_key: Optional[EventKey] = None
    ) -> None:
        """
        Dispatch an event to all registered listeners.

        Args:
            event: Event instance to dispatch
            event_key: Optional Token or Event class. If None, uses type(event).
                      When using a Token, all listeners registered with a Token
                      having the same key (string or type) will be called, even
                      if they are different Token instances.
        """
        if event_key is None:
            event_key = type(event)

        normalized_key = self._normalize_key(event_key)

        listeners = self._listeners.get(normalized_key, [])

        if not listeners:
            logger.debug(f"No listeners registered for {normalized_key}")
            return

        logger.debug(f"Dispatching {normalized_key} to {len(listeners)} listener(s)")

        for priority, handler in listeners:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"Error in event handler {handler.__name__} (priority {priority}) for {normalized_key}: {e}",
                    exc_info=True,
                )

    def unregister(self, event_key: EventKey, handler: Callable) -> None:
        """
        Unregister a specific listener.

        Args:
            event_key: Event class or Token used during registration
            handler: Handler function to remove
        """
        normalized_key = self._normalize_key(event_key)

        if normalized_key not in self._listeners:
            return

        self._listeners[normalized_key] = [
            (p, h) for p, h in self._listeners[normalized_key] if h != handler
        ]

        if not self._listeners[normalized_key]:
            del self._listeners[normalized_key]

        logger.debug(f"Unregistered listener {handler.__name__} for {normalized_key}")

    def clear(self, event_key: EventKey | None = None) -> None:
        """
        Clear all listeners for an event, or all events if None.

        Args:
            event_key: Event class or Token, or None to clear all
        """
        if event_key is None:
            self._listeners.clear()
            logger.debug("Cleared all event listeners")
        else:
            normalized_key = self._normalize_key(event_key)
            if normalized_key in self._listeners:
                del self._listeners[normalized_key]
                logger.debug(f"Cleared all listeners for {normalized_key}")

    def has_listeners(self, event_key: EventKey) -> bool:
        """
        Check if there are any listeners for an event.

        Args:
            event_key: Event class or Token

        Returns:
            True if listeners exist, False otherwise
        """
        normalized_key = self._normalize_key(event_key)
        return (
            normalized_key in self._listeners
            and len(self._listeners[normalized_key]) > 0
        )

    def _normalize_key(self, key: EventKey) -> Token:
        """
        Normalize event key to ensure consistent lookup.

        Args:
            key: Event class or Token

        Returns:
            Normalized key (always returns Token for consistency)
        """
        if isinstance(key, type) and issubclass(key, BaseEvent):
            return Token(key)
        elif isinstance(key, Token):
            return key

        raise TypeError(
            f"Event key must be a BaseEvent subclass or Token[BaseEvent], got {type(key)}"
        )


__all__ = [
    "Bus",
    "EventKey",
]
