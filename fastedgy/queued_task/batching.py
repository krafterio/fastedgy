# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, AsyncIterator, Callable, Iterable

from fastedgy.dependencies import get_service
from fastedgy.queued_task.context import get_context, set_context


async def enqueue_id_range_tasks(
    func: Callable[..., Any],
    ids: Iterable[int],
    *,
    chunk_size: int = 200,
    channel: str | None = None,
    priority: int | None = None,
    max_retries: int | None = None,
    **kwargs: Any,
) -> list[Any]:
    """Fan id-driven work out into queued tasks by contiguous id ranges.

    The ids are deduplicated and sorted ascending, then one task per chunk is
    enqueued as ``func(min_id=..., max_id=..., **kwargs)``. The task is
    expected to re-resolve its own ids within ``[min_id, max_id]`` (fresh
    data, compact arguments) and to iterate them under
    :func:`iter_with_cursor` for an exact resume after a crash or retry.
    """
    from fastedgy.queued_task.services.queued_tasks import QueuedTasks

    queued_tasks = get_service(QueuedTasks)
    sorted_ids = sorted(set(ids))
    tasks: list[Any] = []

    for start in range(0, len(sorted_ids), chunk_size):
        chunk = sorted_ids[start : start + chunk_size]
        task = await queued_tasks.add_task_async(
            func,
            min_id=chunk[0],
            max_id=chunk[-1],
            channel=channel,
            priority=priority,
            max_retries=max_retries,
            **kwargs,
        )
        tasks.append(task)

    return tasks


async def iter_with_cursor(
    ids: Iterable[int],
    *,
    key: str = "cursor",
    commit_every: int = 1,
) -> AsyncIterator[int]:
    """Iterate ids ascending under a resume cursor persisted in the queued
    task context.

    Every ``commit_every`` processed ids, the cursor moves to the last one
    (plus a final commit): a crashed, timed-out or retried run restarts after
    the last committed id instead of from scratch — the worker re-seeds the
    execution context from the persisted ``QueuedTask.context``. Outside a
    queued task the cursor stays process-local (no persistence).
    """
    cursor = get_context(key)
    pending = sorted(item_id for item_id in set(ids) if cursor is None or item_id > cursor)

    processed = 0
    last: int | None = None

    for item_id in pending:
        yield item_id
        processed += 1
        last = item_id
        if processed % commit_every == 0:
            set_context(key, item_id)

    if last is not None and processed % commit_every != 0:
        set_context(key, last)


__all__ = [
    "enqueue_id_range_tasks",
    "iter_with_cursor",
]
