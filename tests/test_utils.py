# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from datetime import datetime
from zoneinfo import ZoneInfo

from fastedgy.serializers import datetime_serializer
from fastedgy.sync import run_async_context_sync
from fastedgy.test.factories import use_request
from fastedgy.timezone import ensure_aware, get_timezone_info


def test_get_timezone_info_returns_zoneinfo() -> None:
    assert isinstance(get_timezone_info(), ZoneInfo)


def test_ensure_aware_passes_through_none_and_aware() -> None:
    assert ensure_aware(None) is None

    aware = datetime(2025, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))

    assert ensure_aware(aware) == aware


def test_ensure_aware_attaches_context_timezone() -> None:
    with use_request(timezone="Europe/Paris"):
        result = ensure_aware(datetime(2025, 1, 1, 12, 0))

        assert result is not None
        assert result.tzinfo == ZoneInfo("Europe/Paris")


def test_datetime_serializer_uses_context_timezone() -> None:
    with use_request(timezone="Europe/Paris"):
        result = datetime_serializer(datetime(2025, 1, 1, 11, 0, tzinfo=ZoneInfo("UTC")))

        assert result == "2025-01-01T12:00:00+01:00"


def test_run_async_context_sync() -> None:
    @asynccontextmanager
    async def resource() -> AsyncGenerator[str, None]:
        yield "ready"

    with run_async_context_sync(resource()) as value:
        assert value == "ready"
