# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata, produce_migrations, render_python_code
from alembic.migration import MigrationContext
from alembic.operations import Operations

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.orm.fields import Translatable
from fastedgy.orm.migration import (
    disable_pg_trgm_extension,
    disable_postgis_extension,
    disable_unaccent_extension,
    disable_vector_extension,
    enable_pg_trgm_extension,
    enable_postgis_extension,
    enable_unaccent_extension,
    enable_vector_extension,
    process_translatable_revision_directives,
)
from fastedgy.orm.migration.translatable import ConvertFromTranslatableOperation, ConvertToTranslatableOperation


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


def test_the_translatable_conversions_write_their_sql_without_a_database() -> None:
    def run(op: Any) -> None:
        op.convert_to_translatable("courses", "title", fallback_locale="en", existing_type=sa.VARCHAR(40))
        op.convert_from_translatable("courses", "title", fallback_locale="en", type_=sa.VARCHAR(40))

    sql = _offline(run)

    assert (
        "ALTER TABLE courses ALTER COLUMN title TYPE JSONB "
        """USING CASE WHEN "title" IS NULL THEN NULL ELSE jsonb_build_object('en', "title") END;"""
    ) in sql
    assert """ALTER TABLE courses ALTER COLUMN title TYPE VARCHAR(40) USING "title" ->> 'en';""" in sql


def _diff(connection: Any, table: sa.Table) -> Any:
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "include_name": lambda name, kind, _: kind != "table" or name == table.name,
        },
    )
    script = produce_migrations(context, table.metadata)
    process_translatable_revision_directives(context, None, [script])

    return script


async def test_a_text_column_turning_translatable_keeps_its_values_as_the_fallback(setup_db: FastEdgy) -> None:
    database = get_service(Registry).database
    translatable = sa.Table(
        "test_translatable_migration",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", Translatable(), nullable=True),
    )
    scripts: list[Any] = []

    await database.execute("DROP TABLE IF EXISTS test_translatable_migration")

    try:
        await database.execute("CREATE TABLE test_translatable_migration (id integer PRIMARY KEY, name varchar(40))")
        await database.execute("INSERT INTO test_translatable_migration VALUES (1, 'Chair'), (2, NULL)")

        async with database.connection() as connection:
            scripts.append(await connection.run_sync(_diff, translatable))

        upgrade = scripts[0].upgrade_ops.ops[0].ops
        downgrade = scripts[0].downgrade_ops.ops[0].ops

        assert [type(op) for op in upgrade] == [ConvertToTranslatableOperation]
        assert [type(op) for op in downgrade] == [ConvertFromTranslatableOperation]
        assert (
            "op.convert_to_translatable('test_translatable_migration', 'name', fallback_locale='en', "
            "existing_type=sa.VARCHAR(length=40))"
        ) in render_python_code(scripts[0].upgrade_ops)

        await _online(lambda op: op.invoke(upgrade[0]))

        rows = await database.fetch_all("SELECT id, name FROM test_translatable_migration ORDER BY id")

        assert [tuple(row) for row in rows] == [(1, {"en": "Chair"}), (2, None)]

        async with database.connection() as connection:
            assert (await connection.run_sync(_diff, translatable)).upgrade_ops.is_empty()

        await _online(lambda op: op.invoke(downgrade[0]))

        rows = await database.fetch_all("SELECT id, name FROM test_translatable_migration ORDER BY id")

        assert [tuple(row) for row in rows] == [(1, "Chair"), (2, None)]
    finally:
        await database.execute("DROP TABLE IF EXISTS test_translatable_migration")


async def test_the_schema_of_a_translatable_model_needs_no_migration(setup_db: FastEdgy) -> None:
    from fastedgy.test.models.course import Course

    def diff(connection: Any) -> list[Any]:
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "include_object": lambda _, name, kind, *__: kind != "table" or name == "test_courses",
            },
        )

        return compare_metadata(context, Course.table.metadata)

    async with get_service(Registry).database.connection() as connection:
        assert await connection.run_sync(diff) == []
