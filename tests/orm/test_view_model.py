# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from sqlalchemy import Column, Integer, MetaData, Table, Text, cast, select
from sqlalchemy.dialects import postgresql

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.orm.migration.view_model import normalize_sql


# --- normalize_sql: parenthesis handling (no database) ---------------------


def test_normalize_sql_keeps_distinct_on_parentheses_single_table() -> None:
    # Single-table view: qualifiers are dropped, but the `DISTINCT ON (...)`
    # parens are required syntax and must survive.
    sql = "SELECT DISTINCT ON (t.grp) t.id FROM t ORDER BY t.grp"

    assert "distinct on (grp)" in normalize_sql(sql)


def test_normalize_sql_keeps_distinct_on_parentheses_with_join() -> None:
    sql = 'SELECT DISTINCT ON (d."user") u.id FROM devices d JOIN users u ON u.id = d."user" ORDER BY d."user"'

    assert "distinct on (d.user)" in normalize_sql(sql)


def test_normalize_sql_keeps_multi_column_distinct_on_parentheses() -> None:
    sql = "SELECT DISTINCT ON (a.x, a.y) a.x FROM a JOIN b ON a.id = b.id"

    assert "distinct on (a.x, a.y)" in normalize_sql(sql)


def test_normalize_sql_strips_join_on_parentheses_but_not_distinct_on() -> None:
    # The `DISTINCT ON (...)` parens are required syntax and must survive; the
    # `JOIN ... ON (...)` grouping parens are redundant and must still be peeled.
    # This proves the fix is scoped to `distinct on (` and does not blanket-protect
    # every `on (`.
    sql = 'SELECT DISTINCT ON (d."user") u.id FROM devices d JOIN users u ON ((u.id = d."user"))'

    normalized = normalize_sql(sql)

    assert "distinct on (d.user)" in normalized
    assert "on u.id = d.user" in normalized
    assert "on (u.id" not in normalized


def test_normalize_sql_still_strips_redundant_grouping_parentheses() -> None:
    sql = "SELECT a.x FROM a JOIN b ON a.id = b.id WHERE (a.x <> a.y)"

    assert normalize_sql(sql).endswith("where a.x <> a.y")


# --- view change detection: false-positive regression (integration) -------


async def _view_definition(database: Any, name: str) -> str:
    row = await database.fetch_one(
        "SELECT view_definition FROM information_schema.views WHERE table_name = :name",
        {"name": name},
    )

    assert row is not None

    return str(row[0])


async def _assert_no_false_positive(database: Any, name: str, selectable: Any) -> None:
    """Mirror the migration view-change detector for ``selectable``.

    1. The normalized model definition must be valid SQL — regression guard: a
       ``DISTINCT ON (...)`` clause must keep its required parens, otherwise the
       ``CREATE VIEW`` below raises.
    2. Its first-level normalization differs from PostgreSQL's stored form (the
       no-op ``CAST`` the model keeps but PostgreSQL discards) — so the deeper DB
       round-trip is actually exercised, not short-circuited.
    3. After a PostgreSQL round-trip both canonical forms match — the detector
       reports no change, i.e. no false positive.
    """
    compiled = str(selectable.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    model_def = normalize_sql(compiled)

    # The "existing" view, as a previous migration / metadata.create_all built it.
    await database.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
    await database.execute(f"CREATE VIEW {name} AS {compiled}")
    db_def = normalize_sql(await _view_definition(database, name), True)

    assert normalize_sql(compiled, True) != db_def

    # The deeper check recreates the view from the normalized model definition
    # (raises here if that definition is invalid SQL) and compares canonical forms.
    await database.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
    await database.execute(f"CREATE VIEW {name} AS {model_def}")
    check_def = normalize_sql(await _view_definition(database, name), True)
    await database.execute(f"DROP VIEW IF EXISTS {name} CASCADE")

    assert check_def == db_def


async def test_single_table_views_have_no_false_positive(setup_db: FastEdgy) -> None:
    database = get_service(Registry).database

    await database.execute("DROP TABLE IF EXISTS test_view_single CASCADE")
    await database.execute("CREATE TABLE test_view_single (id integer PRIMARY KEY, grp integer, val integer)")

    try:
        meta = MetaData()
        src = Table(
            "test_view_single",
            meta,
            Column("id", Integer, primary_key=True),
            Column("grp", Integer),
            Column("val", Integer),
        )

        # `cast(grp AS INTEGER)` is a no-op PostgreSQL drops from its stored form.
        with_distinct = (
            select(src.c.id, cast(src.c.grp, Integer).label("grp"), src.c.val)
            .order_by(src.c.grp, src.c.val.desc())
            .distinct(src.c.grp)
        )
        without_distinct = select(src.c.id, cast(src.c.grp, Integer).label("grp"), src.c.val).where(src.c.val > 0)

        await _assert_no_false_positive(database, "test_view_single_distinct", with_distinct)
        await _assert_no_false_positive(database, "test_view_single_plain", without_distinct)
    finally:
        await database.execute("DROP VIEW IF EXISTS test_view_single_distinct CASCADE")
        await database.execute("DROP VIEW IF EXISTS test_view_single_plain CASCADE")
        await database.execute("DROP TABLE IF EXISTS test_view_single CASCADE")


async def test_join_views_have_no_false_positive(setup_db: FastEdgy) -> None:
    # Mirrors the original bug shape: a JOIN view, with and without `DISTINCT ON`,
    # carrying a no-op cast on the foreign-key column that PostgreSQL discards.
    database = get_service(Registry).database

    await database.execute("DROP TABLE IF EXISTS test_view_device CASCADE")
    await database.execute("DROP TABLE IF EXISTS test_view_owner CASCADE")
    await database.execute("CREATE TABLE test_view_owner (id integer PRIMARY KEY, label text)")
    await database.execute("CREATE TABLE test_view_device (id integer PRIMARY KEY, owner integer, seen_at integer)")

    try:
        meta = MetaData()
        owner = Table("test_view_owner", meta, Column("id", Integer, primary_key=True), Column("label", Text))
        device = Table(
            "test_view_device",
            meta,
            Column("id", Integer, primary_key=True),
            Column("owner", Integer),
            Column("seen_at", Integer),
        )
        joined = device.join(owner, owner.c.id == device.c.owner)

        with_distinct = (
            select(owner.c.id, cast(device.c.owner, Integer).label("owner"), owner.c.label)
            .select_from(joined)
            .order_by(device.c.owner, device.c.seen_at.desc())
            .distinct(device.c.owner)
        )
        without_distinct = (
            select(owner.c.id, cast(device.c.owner, Integer).label("owner"), owner.c.label)
            .select_from(joined)
            .where(device.c.seen_at > 0)
        )

        await _assert_no_false_positive(database, "test_view_join_distinct", with_distinct)
        await _assert_no_false_positive(database, "test_view_join_plain", without_distinct)
    finally:
        await database.execute("DROP VIEW IF EXISTS test_view_join_distinct CASCADE")
        await database.execute("DROP VIEW IF EXISTS test_view_join_plain CASCADE")
        await database.execute("DROP TABLE IF EXISTS test_view_device CASCADE")
        await database.execute("DROP TABLE IF EXISTS test_view_owner CASCADE")
