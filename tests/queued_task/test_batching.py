# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.queued_task import enqueue_id_range_tasks, iter_with_cursor
from fastedgy.queued_task.context import TaskContext, get_context
from fastedgy.test import tasks


async def test_enqueue_id_range_tasks_chunks_sorted_ids(setup_db: FastEdgy) -> None:
    created = await enqueue_id_range_tasks(
        tasks.add_numbers,
        [9, 1, 5, 3, 2, 8, 1],
        chunk_size=2,
        channel="notifications",
        date="2026-07-11",
    )

    ranges = [(task.kwargs["min_id"], task.kwargs["max_id"]) for task in created]
    assert ranges == [(1, 2), (3, 5), (8, 9)]
    assert all(task.channel == "notifications" for task in created)
    assert all(task.kwargs["date"] == "2026-07-11" for task in created)


async def test_enqueue_id_range_tasks_empty(setup_db: FastEdgy) -> None:
    assert await enqueue_id_range_tasks(tasks.add_numbers, []) == []


async def test_iter_with_cursor_resumes_after_persisted_cursor(setup_db: FastEdgy) -> None:
    with TaskContext(None, {"cursor": 3}):
        seen = [item_id async for item_id in iter_with_cursor([1, 2, 3, 4, 5, 6])]
        assert seen == [4, 5, 6]
        assert get_context("cursor") == 6


async def test_iter_with_cursor_commits_progress_per_item(setup_db: FastEdgy) -> None:
    with TaskContext(None, {}):
        iterator = iter_with_cursor([10, 20, 30])

        assert await anext(iterator) == 10
        assert await anext(iterator) == 20
        assert get_context("cursor") == 10

        assert await anext(iterator) == 30
        assert get_context("cursor") == 20

        assert [item_id async for item_id in iterator] == []
        assert get_context("cursor") == 30


async def test_iter_with_cursor_commit_every_batches_the_writes(setup_db: FastEdgy) -> None:
    with TaskContext(None, {}):
        seen = [item_id async for item_id in iter_with_cursor([1, 2, 3, 4, 5], commit_every=2)]
        assert seen == [1, 2, 3, 4, 5]
        assert get_context("cursor") == 5


async def test_iter_with_cursor_outside_task_context(setup_db: FastEdgy) -> None:
    seen = [item_id async for item_id in iter_with_cursor([2, 1])]
    assert seen == [1, 2]


async def test_iter_with_cursor_persists_into_the_task_row(setup_db: FastEdgy) -> None:
    import asyncio

    task = await enqueue_id_range_tasks(tasks.add_numbers, [1], chunk_size=1)
    queued = task[0]

    with TaskContext(queued, {}):
        async for _ in iter_with_cursor([7]):
            pass

    await asyncio.sleep(0.05)
    fresh = await type(queued).query.get(id=queued.id)
    assert fresh.context.get("cursor") == 7
