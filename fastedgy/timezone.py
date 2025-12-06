# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zoneinfo import ZoneInfo


def setup_timezone(timezone: str):
    import os
    import time

    os.environ["TZ"] = timezone
    time.tzset()


def get_timezone() -> str:
    import os

    return os.environ.get("TZ", "UTC")


def get_timezone_info() -> "ZoneInfo":
    from zoneinfo import ZoneInfo

    return ZoneInfo(get_timezone())


__all__ = [
    "setup_timezone",
    "get_timezone",
    "get_timezone_info",
]
