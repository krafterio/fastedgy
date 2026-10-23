# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
from types import SimpleNamespace
from typing import Any, cast

from asyncpg.exceptions import InterfaceError, InternalClientError, UniqueViolationError
from sqlalchemy.engine import ExceptionContext

from fastedgy.orm.transaction import invalidate_desynchronized_connection


def _context(driver_error: Exception) -> Any:
    try:
        try:
            raise driver_error
        except Exception as error:
            raise RuntimeError("adapted by the dialect") from error
    except RuntimeError as adapted:
        return SimpleNamespace(original_exception=adapted, is_disconnect=False, invalidate_pool_on_disconnect=True)


def test_a_connection_still_caught_in_an_earlier_operation_is_dropped_alone() -> None:
    for error in (
        InternalClientError("cannot switch to state 12; another operation (2) is in progress"),
        InterfaceError("cannot perform operation: another operation is in progress"),
    ):
        context = _context(error)

        invalidate_desynchronized_connection(cast(ExceptionContext, context))

        assert (context.is_disconnect, context.invalidate_pool_on_disconnect) == (True, False)


def test_a_statement_error_keeps_its_connection() -> None:
    for error in (UniqueViolationError("duplicate key"), InterfaceError("the connection is closed")):
        context = _context(error)

        invalidate_desynchronized_connection(cast(ExceptionContext, context))

        assert (context.is_disconnect, context.invalidate_pool_on_disconnect) == (False, True)


async def test_the_pool_discards_the_desynchronized_connection(setup_db, monkeypatch) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"], pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as connection:
            broken_pid = await connection.scalar(text("SELECT pg_backend_pid()"))
            adapted = (await connection.get_raw_connection()).dbapi_connection

            async def desynchronized(*args, **kwargs):
                raise InternalClientError("cannot switch to state 12; another operation (2) is in progress")

            monkeypatch.setattr(type(adapted), "_prepare", desynchronized)
            try:
                await connection.execute(text("SELECT 1"))
            except DBAPIError as error:
                assert error.connection_invalidated
            else:
                raise AssertionError("the desynchronized statement did not fail")
            finally:
                monkeypatch.undo()

        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT pg_backend_pid()")) != broken_pid
    finally:
        await engine.dispose()
