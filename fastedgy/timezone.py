# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime
from typing import TYPE_CHECKING, overload

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


@overload
def ensure_aware(value: datetime) -> datetime: ...
@overload
def ensure_aware(value: None) -> None: ...
def ensure_aware(value: datetime | None) -> datetime | None:
    """Attach the current request timezone to a naive datetime.

    Naive datetimes coming from clients (e.g. Flutter's `DateTime.toIso8601String()`
    on a local DateTime drops the offset) must be anchored to a timezone before
    being persisted, otherwise asyncpg/Postgres applies the session timezone —
    UTC by default — and the stored value silently shifts by the user's offset.

    The timezone used is `fastedgy.context.get_timezone()` (the `X-Timezone`
    header from the active request, falling back to the server's `TZ` env var).
    Already-aware datetimes and `None` pass through unchanged.

    Used by `create_item_action` / `patch_item_action`; custom endpoints that
    accept datetime fields outside that pipeline should call this helper too.
    """
    if value is None or value.tzinfo is not None:
        return value
    from fastedgy.context import get_timezone as _ctx_get_timezone

    return value.replace(tzinfo=_ctx_get_timezone())


__all__ = [
    "setup_timezone",
    "get_timezone",
    "get_timezone_info",
    "ensure_aware",
]
