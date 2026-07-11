# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm import with_transaction
from fastedgy.test.models.category import Category


async def test_with_transaction_commits_the_unit(setup_db: FastEdgy) -> None:
    async def op() -> Category:
        category = Category(name="Committed")
        await category.save()

        return category

    result = await with_transaction(op)

    assert result.id is not None
    assert await Category.query.filter(Category.columns.name == "Committed").count() == 1


async def test_with_transaction_rolls_back_on_error(setup_db: FastEdgy) -> None:
    async def op() -> None:
        await Category(name="RolledBack").save()
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await with_transaction(op)

    assert await Category.query.filter(Category.columns.name == "RolledBack").count() == 0


async def test_defer_after_commit_runs_once_after_commit(setup_db: FastEdgy) -> None:
    from fastedgy.orm import defer_after_commit

    fired: list[str] = []

    async def op() -> None:
        defer_after_commit(lambda: fired.append("side effect"))
        await Category(name="Deferred").save()
        assert fired == []

    await with_transaction(op)

    assert fired == ["side effect"]


async def test_defer_after_commit_discarded_on_rollback(setup_db: FastEdgy) -> None:
    from fastedgy.orm import defer_after_commit

    fired: list[str] = []

    async def op() -> None:
        defer_after_commit(lambda: fired.append("ghost"))
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await with_transaction(op)

    assert fired == []


async def test_defer_after_commit_fires_only_for_the_committed_attempt(setup_db: FastEdgy) -> None:
    from sqlalchemy.exc import DBAPIError

    from fastedgy.orm import defer_after_commit

    fired: list[int] = []
    attempts = {"n": 0}

    class _SerializationOrig(Exception):
        sqlstate = "40001"

    async def op() -> None:
        attempts["n"] += 1
        defer_after_commit(lambda n=attempts["n"]: fired.append(n))
        if attempts["n"] == 1:
            raise DBAPIError("UPDATE", None, _SerializationOrig())

    await with_transaction(op)

    assert attempts["n"] == 2
    assert fired == [2]


async def test_with_transaction_restores_request_context_on_replay(setup_db: FastEdgy) -> None:
    from typing import Any, cast

    from sqlalchemy.exc import DBAPIError

    from fastedgy import context
    from fastedgy.http import Request

    class _SerializationOrig(Exception):
        sqlstate = "40001"

    token = context.set_request(
        Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": []})
    )
    try:
        initial = cast(Any, object())
        mutated = cast(Any, object())
        context.set_workspace(initial)

        seen: list[Any] = []

        async def op() -> None:
            seen.append(context.get_workspace())
            context.set_workspace(mutated)
            if len(seen) == 1:
                raise DBAPIError("INSERT", None, _SerializationOrig())

        await with_transaction(op)

        # The replay starts from the pre-transaction context, not the
        # rolled-back attempt's mutation; the committed attempt's one is kept.
        assert seen == [initial, initial]
        assert context.get_workspace() is mutated
    finally:
        context.reset_request(token)


async def test_defer_after_commit_runs_immediately_without_transaction(setup_db: FastEdgy) -> None:
    from fastedgy.orm import defer_after_commit

    fired: list[str] = []
    defer_after_commit(lambda: fired.append("now"))

    assert fired == ["now"]


async def test_defer_after_commit_nested_waits_for_outermost_commit(setup_db: FastEdgy) -> None:
    from fastedgy.orm import defer_after_commit

    fired: list[str] = []

    async def inner() -> None:
        defer_after_commit(lambda: fired.append("inner"))

    async def outer() -> None:
        await with_transaction(inner)
        assert fired == []

    await with_transaction(outer)

    assert fired == ["inner"]
