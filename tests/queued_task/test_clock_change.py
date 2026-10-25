# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

import pytest

import fastedgy.context as fastedgy_context
import fastedgy.queued_task.models.queued_task_worker as worker_module
import fastedgy.queued_task.scheduler.service as scheduler_module
from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.queued_task.scheduler.cron_scheduler import CronScheduler
from fastedgy.queued_task.scheduler.service import Scheduler
from fastedgy.test.models.queued_task_worker import QueuedTaskWorker

PARIS = ZoneInfo("Europe/Paris")


def _frozen_at(instant: datetime) -> type[datetime]:
    class Frozen(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    return Frozen


def _fires(cron: str, start: datetime, end: datetime) -> list[datetime]:
    scheduler = CronScheduler()
    fires = []
    minute = start

    while minute <= end:
        if scheduler._cron_matches(cron, minute.astimezone(PARIS)):
            fires.append(minute)
        minute += timedelta(minutes=1)

    return fires


def test_a_daily_cron_in_the_repeated_hour_fires_once_on_the_autumn_change() -> None:
    fires = _fires("0 2 * * *", datetime(2026, 10, 24, 22, tzinfo=UTC), datetime(2026, 10, 25, 4, tzinfo=UTC))

    assert fires == [datetime(2026, 10, 25, 0, tzinfo=UTC)]


def test_an_hourly_cron_fires_in_both_halves_of_the_repeated_hour() -> None:
    fires = _fires("0 * * * *", datetime(2026, 10, 24, 23, tzinfo=UTC), datetime(2026, 10, 25, 3, tzinfo=UTC))

    assert fires == [datetime(2026, 10, 24, 23, tzinfo=UTC)] + [
        datetime(2026, 10, 25, hour, tzinfo=UTC) for hour in range(4)
    ]


@pytest.mark.parametrize("cron", ["0 2 * * *", "30 2 * * *"])
def test_a_daily_cron_in_the_skipped_hour_fires_after_the_gap_on_the_spring_change(cron: str) -> None:
    fires = _fires(cron, datetime(2027, 3, 27, 23, tzinfo=UTC), datetime(2027, 3, 28, 3, tzinfo=UTC))

    assert fires == [datetime(2027, 3, 28, 1, tzinfo=UTC)]


async def test_a_heartbeat_a_minute_old_is_alive_across_the_spring_change(
    setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fastedgy_context, "get_timezone", lambda: PARIS)
    monkeypatch.setattr(worker_module, "datetime", _frozen_at(datetime(2027, 3, 28, 1, 0, 30, tzinfo=UTC)))
    worker = QueuedTaskWorker(server_name="server-clock")
    worker.last_heartbeat = datetime(2027, 3, 28, 0, 59, 30, tzinfo=UTC).astimezone(PARIS)

    assert worker.is_alive is True


async def test_a_task_delayed_an_hour_runs_an_hour_later_across_the_autumn_change(
    setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fastedgy_context, "get_timezone", lambda: PARIS)
    monkeypatch.setattr(scheduler_module, "datetime", _frozen_at(datetime(2026, 10, 25, 0, 30, tzinfo=UTC)))

    task = await get_service(Scheduler).schedule("os.getcwd", run_at=timedelta(hours=1))

    assert task.date_enqueued == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
