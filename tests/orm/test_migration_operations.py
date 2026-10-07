# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io
from collections.abc import Callable
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.orm.migration import (
    disable_pg_trgm_extension,
    disable_postgis_extension,
    disable_unaccent_extension,
    disable_vector_extension,
    enable_pg_trgm_extension,
    enable_postgis_extension,
    enable_unaccent_extension,
    enable_vector_extension,
)


def _offline(run: Callable[[Operations], None]) -> str:
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})

    with Operations.context(context) as operations:
        run(operations)

    return buffer.getvalue()


def test_the_enum_operations_write_their_sql_without_a_database() -> None:
    def run(op: Any) -> None:
        op.create_enum("status", ["draft", "done"])
        op.replace_enum(
            "status",
            ["done", "archived"],
            ["draft", "done"],
            {"draft": "archived"},
            {"tasks": {"status": "done"}},
            {"tasks": {"status": "draft"}},
        )
        op.drop_enum("status", ["done", "archived"])

    sql = _offline(run)

    assert "CREATE TYPE status AS ENUM ('draft', 'done');" in sql
    assert "ALTER TYPE status RENAME TO status_old;" in sql
    assert "CREATE TYPE status AS ENUM ('done', 'archived');" in sql
    assert "WHEN __fastedgy_enum_column__::text = 'draft' THEN 'archived'::status" in sql
    assert "SET DEFAULT ' || $default$'done'::status$default$" in sql
    assert "DROP TYPE IF EXISTS status_old;" in sql
    assert "DROP TYPE IF EXISTS status;" in sql


def test_the_extensions_write_their_sql_without_a_database() -> None:
    def run(_: Any) -> None:
        enable_unaccent_extension()
        enable_pg_trgm_extension()
        enable_vector_extension()
        enable_postgis_extension()
        disable_postgis_extension()
        disable_vector_extension()
        disable_pg_trgm_extension()
        disable_unaccent_extension()

    sql = _offline(run)

    for extension in ("unaccent", "pg_trgm", "vector", "postgis"):
        assert f"CREATE EXTENSION IF NOT EXISTS {extension};" in sql
        assert f"DROP EXTENSION IF EXISTS {extension} CASCADE;" in sql


async def _online(run: Callable[[Any], None]) -> None:
    def migrate(connection: Any) -> None:
        with Operations.context(MigrationContext.configure(connection)) as operations:
            run(operations)

    async with get_service(Registry).database.connection() as connection:
        await connection.run_sync(migrate)


async def test_replacing_an_enum_maps_its_values_and_keeps_the_default_of_its_columns(setup_db: FastEdgy) -> None:
    database = get_service(Registry).database

    await database.execute("DROP TABLE IF EXISTS test_enum_task")
    await database.execute("DROP TYPE IF EXISTS test_enum_status")
    await database.execute("DROP TYPE IF EXISTS test_enum_status_old")

    try:
        await _online(lambda op: op.create_enum("test_enum_status", ["draft", "done"]))
        await _online(lambda op: op.create_enum("test_enum_status", ["ignored"]))
        await database.execute(
            "CREATE TABLE test_enum_task "
            "(id integer PRIMARY KEY, status test_enum_status NOT NULL DEFAULT 'done', step test_enum_status)"
        )
        await database.execute("INSERT INTO test_enum_task VALUES (1, 'draft', 'draft'), (2, 'done', 'done')")

        await _online(
            lambda op: op.replace_enum(
                "test_enum_status",
                ["done", "archived"],
                ["draft", "done"],
                None,
                {"test_enum_task": {"status": "done"}},
                {"test_enum_task": {"status": "done"}},
            )
        )

        rows = await database.fetch_all("SELECT id, status::text, step::text FROM test_enum_task ORDER BY id")
        default = await database.fetch_val(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'test_enum_task' AND column_name = 'status'"
        )
        old_type = await database.fetch_val("SELECT count(*) FROM pg_type WHERE typname = 'test_enum_status_old'")

        assert [tuple(row) for row in rows] == [(1, "done", None), (2, "done", "done")]
        assert default == "'done'::test_enum_status"
        assert old_type == 0
    finally:
        await database.execute("DROP TABLE IF EXISTS test_enum_task")
        await database.execute("DROP TYPE IF EXISTS test_enum_status")
        await database.execute("DROP TYPE IF EXISTS test_enum_status_old")
