# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Any

from fastedgy.bus import BaseEvent

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.realtime.manager import Connection


class OnRealtimeFrameEvent(BaseEvent):
    def __init__(self, connection: "Connection", user: "User", event_type: str, data: dict[str, Any]) -> None:
        self.connection = connection
        self.user = user
        self.event_type = event_type
        self.data = data


class OnRealtimeDisconnectEvent(BaseEvent):
    def __init__(self, connection: "Connection", user: "User") -> None:
        self.connection = connection
        self.user = user


class OnRealtimeDeliveredEvent(BaseEvent):
    def __init__(self, event_type: str, data: Any, watchers: dict[int, set[str]]) -> None:
        self.event_type = event_type
        self.data = data
        self.watchers = watchers


__all__ = [
    "OnRealtimeDeliveredEvent",
    "OnRealtimeDisconnectEvent",
    "OnRealtimeFrameEvent",
]
