# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
import logging

from fastedgy.dependencies import get_service
from fastedgy.queued_task.scheduler.decorators import scheduled_task
from fastedgy.storage.services import Storage, StorageUsage

logger = logging.getLogger("fastedgy.storage")

GIB = 1024**3


def usage_line(usage: StorageUsage) -> str:
    """The storage-metrics line: one JSON object, its numbers suffixed `_int` / `_float` as OVHcloud Logs Data
    Platform requires. Written to stdout rather than through logging, so that LOG_LEVEL never filters it out."""
    data_gib = round(usage.data_bytes / GIB, 3)
    cache_gib = round(usage.cache_bytes / GIB, 3)

    return json.dumps(
        {
            "message": f"storage {usage.data_files} files {data_gib} GiB, cache {usage.cache_files} files {cache_gib} GiB",
            "logger": "storage-metrics",
            "metric": "storage",
            "storage_data_objects_int": usage.data_files,
            "storage_data_gib_float": data_gib,
            "storage_cache_objects_int": usage.cache_files,
            "storage_cache_gib_float": cache_gib,
        }
    )


@scheduled_task(cron="0 3 * * *", description="Delete the optimized images older than CACHE_MAX_AGE_DAYS")
async def cleanup_image_cache() -> None:
    deleted = await get_service(Storage).cleanup_image_cache()
    logger.info(f"Deleted {deleted} cached image(s)")


@scheduled_task(cron="17 * * * *", description="Write the storage-metrics line: stored files and image cache")
async def report_storage_usage() -> None:
    print(usage_line(await get_service(Storage).usage()), flush=True)
