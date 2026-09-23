# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import sys
import time
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from fastedgy.test.factories import use_request
from fastedgy.timezone import (
    Timezone,
    get_request_timezone,
    get_timezone,
    get_timezone_info,
    get_timezones_at_hour,
    get_zone_info,
    setup_timezone,
)


@pytest.fixture
def isolated_timezone(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    tzset_calls: list[str] = []
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.delenv("FASTEDGY_TIMEZONE", raising=False)
    monkeypatch.setattr(time, "tzset", lambda: tzset_calls.append(os.environ["TZ"]), raising=False)

    return tzset_calls


def test_setup_timezone_on_windows_leaves_tz_to_the_system(
    monkeypatch: pytest.MonkeyPatch, isolated_timezone: list[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    setup_timezone("America/Guadeloupe")

    assert "TZ" not in os.environ
    assert isolated_timezone == []
    assert get_timezone() == "America/Guadeloupe"


def test_setup_timezone_on_unix_applies_tz_to_the_process(
    monkeypatch: pytest.MonkeyPatch, isolated_timezone: list[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    setup_timezone("America/Guadeloupe")

    assert isolated_timezone == ["America/Guadeloupe"]
    assert get_timezone() == "America/Guadeloupe"


def test_timezone_choices_are_the_iana_keys() -> None:
    assert Timezone["America/Guadeloupe"].name == "America/Guadeloupe"


def test_zone_info_falls_back_to_the_server_timezone() -> None:
    assert get_zone_info(Timezone["America/Guadeloupe"]) == ZoneInfo("America/Guadeloupe")
    assert get_zone_info("Mars/Olympus_Mons") == get_timezone_info()
    assert get_zone_info(None) == get_timezone_info()


def test_request_timezone_is_the_one_the_client_sent() -> None:
    with use_request(timezone="America/Guadeloupe"):
        assert get_request_timezone() == "America/Guadeloupe"


def test_request_timezone_without_client_timezone_is_the_server_one() -> None:
    with use_request():
        assert get_request_timezone() == get_timezone()


def test_timezones_at_hour_are_grouped_by_local_date() -> None:
    timezones = get_timezones_at_hour(13, datetime(2026, 9, 14, 23, 20, tzinfo=UTC))

    assert "Pacific/Honolulu" in timezones[date(2026, 9, 14)]
    assert "Pacific/Kiritimati" in timezones[date(2026, 9, 15)]
    assert all("Europe/Paris" not in keys for keys in timezones.values())


def test_timezones_at_hour_reach_a_half_hour_timezone_once_a_day() -> None:
    hits = [
        day
        for hour in range(24)
        for day, keys in get_timezones_at_hour(19, datetime(2026, 9, 14, hour, tzinfo=UTC)).items()
        if "Asia/Kolkata" in keys
    ]

    assert hits == [date(2026, 9, 14)]
