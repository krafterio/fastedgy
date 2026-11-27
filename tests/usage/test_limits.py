# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from fastedgy.dependencies import register_service
from fastedgy.orm.fields import ChoiceEnum
from fastedgy.test.factories import use_request
from fastedgy.usage import (
    LimitWindow,
    QuotaExceeded,
    Reach,
    UsageCounter,
    UsageLimit,
    UsageQuotas,
    UsageSource,
    check_limits,
    quota_entries,
    window_bounds,
)


class Quota(ChoiceEnum):
    letters = "Letters"
    parcels = "Parcels"


class Sent(UsageCounter):
    def __init__(self) -> None:
        self.sent: list[datetime] = []

    async def used(self, quota: ChoiceEnum, reach: Reach, starts: list[datetime]) -> list[int]:
        return [sum(1 for at in self.sent if at >= start) for start in starts]


class Plan(UsageSource):
    limits_of: list[UsageLimit] = []

    async def limits(self, reach: Reach) -> list[UsageLimit]:
        return self.limits_of

    def refusal(self, quota: ChoiceEnum, window: LimitWindow, limit: int, reset_at: datetime) -> str:
        return f"{limit} {quota.name} a {window.name}"


WORKSPACE = SimpleNamespace(id=7, created_at=datetime(2026, 1, 1, 9, tzinfo=UTC))


@pytest.fixture
def sent() -> Iterator[Sent]:
    counter = Sent()
    quotas = UsageQuotas()
    quotas.count(Quota.letters, counter)
    register_service(quotas, key=UsageQuotas, force=True)
    register_service(Plan(), key=UsageSource, force=True)

    yield counter

    register_service(UsageQuotas(), key=UsageQuotas, force=True)
    register_service(UsageSource(), key=UsageSource, force=True)


def test_a_day_and_a_month_are_those_of_the_timezone_of_the_request() -> None:
    reach = Reach(anchor=WORKSPACE.created_at, workspace_id=7)
    paris = ZoneInfo("Europe/Paris")
    now = datetime(2026, 3, 28, 23, 30, tzinfo=UTC)

    with use_request(timezone="Europe/Paris"):
        day = window_bounds(LimitWindow.day, reach, now)
        month = window_bounds(LimitWindow.month, reach, now)

    # Half past midnight on the 29th in Paris, the day the clocks move forward: a day of 23 hours.
    assert day == (datetime(2026, 3, 29, tzinfo=paris), datetime(2026, 3, 30, tzinfo=paris))
    assert month == (datetime(2026, 3, 1, tzinfo=paris), datetime(2026, 4, 1, tzinfo=paris))
    assert window_bounds(LimitWindow.week, reach, now)[0] == datetime(2026, 3, 26, 9, tzinfo=UTC)
    assert window_bounds(LimitWindow.rolling_5h, reach, now) == (datetime(2026, 3, 28, 18, 30, tzinfo=UTC), None)


async def test_a_usage_is_refused_once_what_it_adds_reaches_the_limit_of_its_quota(sent: Sent) -> None:
    Plan.limits_of = [UsageLimit(Quota.letters, LimitWindow.day, 3), UsageLimit(Quota.parcels, LimitWindow.day, 0)]
    sent.sent = [datetime.now(UTC)] * 2

    with use_request(timezone="UTC"):
        await check_limits(Quota.letters, workspace=WORKSPACE)

        with pytest.raises(QuotaExceeded) as refused:
            await check_limits(Quota.letters, pending=1, workspace=WORKSPACE)

        sent.sent = []
        await check_limits(Quota.letters, pending=2, workspace=WORKSPACE)

    assert (refused.value.status_code, refused.value.message) == (403, "3 letters a day")
    assert (refused.value.quota, refused.value.window, refused.value.limit) == (Quota.letters, LimitWindow.day, 3)
    assert refused.value.reset_at > datetime.now(UTC)


async def test_a_quota_without_a_limit_is_never_counted_nor_refused(sent: Sent) -> None:
    Plan.limits_of = []

    await check_limits(Quota.parcels, pending=1000, workspace=WORKSPACE)


async def test_the_entries_of_a_quota_are_its_limited_windows_and_those_asked_for(sent: Sent) -> None:
    Plan.limits_of = [UsageLimit(Quota.letters, LimitWindow.month, 10)]
    sent.sent = [datetime.now(UTC)] * 4
    reach = Reach(anchor=WORKSPACE.created_at, workspace_id=7)

    with use_request(timezone="UTC"):
        entries = await quota_entries(reach, Quota.letters, shown=(LimitWindow.day, LimitWindow.month))

    assert [(entry.window, entry.used, entry.limit) for entry in entries] == [
        (LimitWindow.day, 4, None),
        (LimitWindow.month, 4, 10),
    ]
