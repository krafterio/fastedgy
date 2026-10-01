# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

import rich_click as click

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.queued_task.scheduler import ScheduledTaskRegistry, register_scheduler_cli_commands
from fastedgy.storage import Storage, StorageUsage
from fastedgy.storage.scheduler import report_storage_usage


async def test_fastedgy_registers_its_storage_tasks(setup_db: FastEdgy) -> None:
    group = click.Group()

    register_scheduler_cli_commands(group)
    registry = get_service(ScheduledTaskRegistry)

    cleanup, report = registry.get("cleanup-image-cache"), registry.get("report-storage-usage")

    assert cleanup is not None and cleanup.cron == "0 3 * * *"
    assert report is not None and report.cron == "17 * * * *"
    assert "scheduler" in group.commands


async def test_report_storage_usage_writes_one_storage_metrics_line(setup_db: FastEdgy, monkeypatch, capsys) -> None:
    async def usage() -> StorageUsage:
        return StorageUsage(data_files=3, data_bytes=3 * 1024**3, cache_files=2, cache_bytes=1024**3 // 2)

    monkeypatch.setattr(get_service(Storage), "usage", usage)

    await report_storage_usage()

    line = json.loads(capsys.readouterr().out)
    assert line["logger"] == "storage-metrics"
    assert line["metric"] == "storage"
    assert (line["storage_data_objects_int"], line["storage_data_gib_float"]) == (3, 3.0)
    assert (line["storage_cache_objects_int"], line["storage_cache_gib_float"]) == (2, 0.5)
