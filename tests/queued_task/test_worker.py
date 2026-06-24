# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime, timedelta, timezone

from fastedgy.app import FastEdgy
from fastedgy.test.models.queued_task_worker import QueuedTaskWorker


async def test_mark_as_started(setup_db: FastEdgy) -> None:
    worker = QueuedTaskWorker(server_name="server-1")
    worker.mark_as_started(max_workers=4)

    assert worker.is_running is True
    assert worker.max_workers == 4
    assert worker.started_at is not None


async def test_update_stats_totals_workers(setup_db: FastEdgy) -> None:
    worker = QueuedTaskWorker(server_name="server-2")
    worker.update_stats(active=2, idle=3)

    assert worker.active_workers == 2
    assert worker.idle_workers == 3
    assert worker.total_workers == 5
    assert worker.is_running is True


async def test_mark_as_stopped_resets_counters(setup_db: FastEdgy) -> None:
    worker = QueuedTaskWorker(server_name="server-3")
    worker.mark_as_started(max_workers=4)
    worker.update_stats(active=2, idle=2)
    worker.mark_as_stopped()

    assert worker.is_running is False
    assert worker.active_workers == 0
    assert worker.idle_workers == 0


async def test_is_alive_depends_on_heartbeat(setup_db: FastEdgy) -> None:
    worker = QueuedTaskWorker(server_name="server-4")

    worker.last_heartbeat = datetime.now(timezone.utc)
    assert worker.is_alive is True

    worker.last_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert worker.is_alive is False


async def test_worker_persists_to_the_database(setup_db: FastEdgy) -> None:
    worker = QueuedTaskWorker(server_name="server-5", max_workers=2)
    await worker.save()

    fetched = await QueuedTaskWorker.query.filter(QueuedTaskWorker.columns.server_name == "server-5").get()

    assert fetched.id == worker.id
    assert fetched.max_workers == 2
    assert fetched.last_heartbeat is not None
