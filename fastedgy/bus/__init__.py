# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.bus.base import BaseEvent
from fastedgy.bus.decorators import on_event
from fastedgy.bus.service import Bus, EventKey

__all__ = [
    "BaseEvent",
    "Bus",
    "EventKey",
    "on_event",
]
