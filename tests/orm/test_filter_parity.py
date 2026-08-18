# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Parity fixtures pinning the Query Builder semantics for client replicas.

Seeds the toolkit models, runs a set of X-Filter/order_by cases through the
real ORM (``filter_query``/``inject_order_by``) and writes everything a client
query engine needs — serialized records, model metadata and expected ids — to
``tests/orm/fixtures/filter_parity.json``. flutter_fastedgy replays the same
cases against its local replica compiler (``test/offline/filter_parity_test.dart``):
both sides must agree.

Run with ``REGEN_PARITY=1`` to rewrite the fixtures after a semantic change
(the default run fails when the results drift from the committed file), and
set ``FILTER_PARITY_OUT=/path/to/flutter_fastedgy/test/offline/fixtures/filter_parity.json``
to also refresh the client copy.
"""

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastedgy.metadata_model.generator import add_inverse_relations, generate_metadata_model
from fastedgy.orm.field_selector import filter_selected_fields
from fastedgy.orm.filter import filter_query
from fastedgy.orm.order_by import inject_order_by

PARITY_PATH = Path(__file__).parent / "fixtures/filter_parity.json"

CASES: list[dict[str, Any]] = [
    {"model": "product", "filter": ["name", "=", "Laptop Pro"]},
    {"model": "product", "filter": ["name", "!=", "Laptop Pro"]},
    {"model": "product", "filter": ["name", "like", "Lap%"]},
    {"model": "product", "filter": ["name", "like", "lap%"]},
    {"model": "product", "filter": ["name", "ilike", "lap%"]},
    {"model": "product", "filter": ["name", "not like", "Lap%"]},
    {"model": "product", "filter": ["name", "not ilike", "lap%"]},
    {"model": "product", "filter": ["name", "contains", "aptop"]},
    {"model": "product", "filter": ["name", "contains", "APTOP"]},
    {"model": "product", "filter": ["name", "icontains", "APTOP"]},
    {"model": "product", "filter": ["name", "not contains", "aptop"]},
    {"model": "product", "filter": ["name", "not icontains", "APTOP"]},
    {"model": "product", "filter": ["name", "starts with", "Lap"]},
    {"model": "product", "filter": ["reference", "starts with", "aaaaaaaa"]},
    {"model": "product", "filter": ["reference", "icontains", "bbbb"]},
    {"model": "product", "filter": ["name", "not starts with", "Lap"]},
    {"model": "product", "filter": ["name", "ends with", "mini"]},
    {"model": "product", "filter": ["name", "not ends with", "mini"]},
    {"model": "product", "filter": ["description", "not icontains", "great"]},
    {"model": "product", "filter": ["price", ">=", 500]},
    {"model": "product", "filter": ["price", "between", [10, 600]]},
    {"model": "product", "filter": ["quantity", "in", [0, 5]]},
    {"model": "product", "filter": ["quantity", "not in", [0, 5]]},
    {"model": "product", "filter": ["is_active", "is true"]},
    {"model": "product", "filter": ["is_active", "is false"]},
    {"model": "product", "filter": ["rating", "is empty"]},
    {"model": "product", "filter": ["rating", "is not empty"]},
    {"model": "product", "filter": ["rating", ">", 4]},
    {"model": "product", "filter": ["released_on", ">=", "2024-01-01"]},
    {"model": "product", "filter": ["published_at", "<", "2024-06-01T00:00:00"]},
    # Bounds a date range picker produces, including the boundary values
    # themselves: "between" is inclusive on both ends, and a half-open pair is
    # how a calendar bucket is expressed.
    {"model": "product", "filter": ["released_on", "<=", "2024-03-01"]},
    {"model": "product", "filter": ["released_on", "between", ["2023-11-15", "2024-03-01"]]},
    {
        "model": "product",
        "filter": [["released_on", ">=", "2024-03-01"], ["released_on", "<", "2024-04-01"]],
    },
    {"model": "product", "filter": ["published_at", ">=", "2024-03-01T12:00:00"]},
    {"model": "product", "filter": ["published_at", "<=", "2024-03-01T12:00:00"]},
    {
        "model": "product",
        "filter": ["published_at", "between", ["2023-11-15T09:30:00", "2024-06-10T08:00:00"]],
    },
    # A date-only bound on a datetime field: both engines must cut at midnight,
    # so the upper bound excludes that whole day.
    {"model": "product", "filter": ["published_at", ">=", "2024-03-01"]},
    {"model": "product", "filter": ["published_at", "between", ["2024-03-01", "2024-06-10"]]},
    {"model": "product", "filter": ["category", "is empty"]},
    {"model": "product", "filter": ["category", "is not empty"]},
    # A many2one leaf compared to an id: the server rewrites the leaf to
    # ``category.id`` and joins the related table, a replica compares the bare
    # FK column. Two plans that must agree, rows with no relation included.
    {"model": "product", "filter": ["category", "=", 1]},
    {"model": "product", "filter": ["category", "!=", 1]},
    {"model": "product", "filter": ["category", "in", [1, 2]]},
    {"model": "product", "filter": ["category", "not in", [1]]},
    {
        "model": "product",
        "filter": ["&", [["category", "=", 1], ["is_active", "is true"]]],
    },
    {"model": "product", "filter": ["category", "=", 3]},
    {"model": "product", "filter": ["category.name", "=", "Electronics"]},
    {"model": "product", "filter": ["tags.name", "=", "urgent"]},
    {"model": "product", "filter": ["tags.name", "icontains", "A"]},
    {
        "model": "product",
        "filter": ["&", [["tags.name", "icontains", "u"], ["tags.name", "!=", "urgent"]]],
    },
    {
        "model": "product",
        "filter": ["|", [["tags.name", "=", "urgent"], ["quantity", ">", 90]]],
    },
    {"model": "product", "filter": ["annotations.body", "icontains", "warranty"]},
    {
        "model": "product",
        "filter": ["|", [["annotations.body", "icontains", "fragile"], ["tags.name", "=", "urgent"]]],
    },
    {"model": "category", "filter": ["annotations.body", "starts with", "Cat"]},
    {"model": "annotation", "filter": ["anchor.$model", "=", "product"]},
    {
        "model": "annotation",
        "filter": ["&", [["anchor.$model", "=", "category"], ["body", "icontains", "note"]]],
    },
    {"model": "product", "filter": ["category.description", "is empty"]},
    {"model": "category", "filter": ["products.is_active", "is true"]},
    {"model": "category", "filter": ["products.name", "ilike", "%novel%"]},
    {
        # Same-related-row semantics: rules on one to-many path must
        # constrain the same product (joined lookups, not independent EXISTS).
        "model": "category",
        "filter": [["products.name", "=", "Laptop Pro"], ["products.is_active", "is false"]],
    },
    {
        "model": "product",
        "filter": ["|", [["category.name", "=", "Books"], ["price", "<", 10]]],
    },
    {
        "model": "product",
        "filter": [
            ["is_active", "is true"],
            ["|", [["quantity", ">", 3], ["name", "ends with", "mini"]]],
        ],
    },
    {"model": "product", "order_by": "name,id"},
    {"model": "product", "order_by": "price:desc,id"},
    {"model": "product", "order_by": "rating,id"},
    {"model": "product", "order_by": "rating:desc,id"},
    {"model": "product", "order_by": "category.name,id"},
    {"model": "product", "order_by": "category.name:desc,id"},
    {"model": "product", "order_by": "name,id", "limit": 2, "offset": 1},
    # Ordering through a relation that fans out ranks a record by an aggregate
    # of the far side, never by a joined row: ascending takes its smallest
    # related value, descending its largest, and a record with nothing related
    # sorts as NULL. One row per record, so `limit`/`offset` count records.
    {"model": "category", "order_by": "products.price,id"},
    {"model": "category", "order_by": "products.price:desc,id"},
    {"model": "category", "order_by": "products.price,id", "limit": 2, "offset": 1},
    {"model": "product", "order_by": "tags.name,id"},
    {"model": "product", "order_by": "tags.name:desc,id"},
    # Workspace extra fields live in a single JSON column and the server reads
    # them with ``extra ->> 'name'``, so every comparison is textual: "10"
    # sorts before "2".
    {"model": "product", "filter": ["extra_owner", "=", "ada"]},
    {"model": "product", "filter": ["extra_owner", "is empty"]},
    {"model": "product", "filter": ["extra_priority", "=", "1"]},
    {"model": "product", "order_by": "extra_priority,id"},
    {"model": "product", "order_by": "extra_priority:desc,id"},
]


async def _seed() -> None:
    from fastedgy.test.models.category import Category
    from fastedgy.test.models.product import Product

    electronics = Category(name="Electronics", description="Devices")
    books = Category(name="Books", description=None)
    empty = Category(name="Empty", description="No product")

    for category in (electronics, books, empty):
        await category.save()

    products = [
        Product(
            name="Laptop Pro",
            description="A great laptop",
            price="999.99",
            is_active=False,
            quantity=5,
            rating=4.5,
            released_on=date(2024, 3, 1),
            published_at=datetime(2024, 3, 1, 12, 0, 0),
            reference=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
            category=electronics,
            extra={"priority": 2, "owner": "ada"},
        ),
        Product(
            name="laptop mini",
            description=None,
            price="499.00",
            is_active=True,
            quantity=0,
            rating=None,
            released_on=date(2023, 11, 15),
            published_at=datetime(2023, 11, 15, 9, 30, 0),
            reference=UUID("bbbbbbbb-0000-0000-0000-000000000002"),
            category=electronics,
            extra={"priority": 10, "owner": "grace"},
        ),
        Product(
            name="Novel",
            description="A short novel",
            price="9.50",
            is_active=True,
            quantity=12,
            rating=3.9,
            released_on=None,
            published_at=None,
            reference=None,
            category=books,
            extra={"priority": 1},
        ),
        Product(
            name="Mystery box",
            description=None,
            price="49.90",
            is_active=True,
            quantity=3,
            rating=None,
            released_on=date(2024, 6, 10),
            published_at=datetime(2024, 6, 10, 8, 0, 0),
            reference=None,
            category=None,
            extra=None,
        ),
    ]

    for product in products:
        await product.save()

    from fastedgy.test.models.annotation import Annotation
    from fastedgy.test.models.tag import Tag

    urgent = Tag(name="urgent")
    sale = Tag(name="sale")
    new = Tag(name="new")

    for tag in (urgent, sale, new):
        await tag.save()

    await products[0].tags.add(urgent)
    await products[0].tags.add(sale)
    await products[1].tags.add(sale)
    await products[2].tags.add(new)

    annotations = [
        Annotation(body="Extended warranty", anchor=products[0]),
        Annotation(body="Fragile item", anchor=products[1]),
        Annotation(body="Category note", anchor=electronics),
        Annotation(body="Catalog review", anchor=books),
    ]

    for annotation in annotations:
        await annotation.save()


async def _run_case(model_cls: Any, case: dict[str, Any]) -> list[int]:
    query = model_cls.query.get_queryset()

    if case.get("filter") is not None:
        query = filter_query(query, json.dumps(case["filter"]))

    if case.get("order_by"):
        query = inject_order_by(query, case["order_by"])

    if case.get("offset"):
        query = query.offset(case["offset"])

    if case.get("limit"):
        query = query.limit(case["limit"])

    return [item.id for item in await query.all()]


PARITY_EPOCH = "2000-01-01 00:00:00+00"


async def _freeze_timestamps(model_classes: Any) -> None:
    """Pin the audit columns the seed stamps with the clock.

    They take part in no case, but they land in the record dump, so leaving
    them on wall-clock time rewrites the fixture on every regeneration.
    Deriving them from the row id keeps them distinct, so a future case
    ordering on them still has a reproducible answer.
    """
    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry

    database = get_service(Registry).database

    for model_cls in model_classes:
        # The epoch carries its UTC offset and goes in as a literal: the audit
        # columns are timestamptz, so a naive value would be read in the
        # server's timezone and the fixture would differ between a laptop and
        # CI. Pinning the instant makes the dump independent of both.
        await database.execute(
            f"UPDATE {model_cls.meta.tablename} SET "
            f"created_at = TIMESTAMPTZ '{PARITY_EPOCH}' + (id * interval '1 second'), "
            f"updated_at = TIMESTAMPTZ '{PARITY_EPOCH}' + (id * interval '1 second')"
        )


async def _build_parity() -> dict[str, Any]:
    from fastedgy.test.models.annotation import Annotation
    from fastedgy.test.models.category import Category
    from fastedgy.test.models.product import Product
    from fastedgy.test.models.tag import Tag

    model_classes = {"product": Product, "category": Category, "tag": Tag, "annotation": Annotation}
    await _seed()
    await _freeze_timestamps(model_classes.values())

    metadatas = {name: await generate_metadata_model(cls) for name, cls in model_classes.items()}
    add_inverse_relations({model_classes[name]: metadata for name, metadata in metadatas.items()})

    # Relation payloads the replica mirrors on top of the scalar dump: m2m as
    # id lists (pivot rows), generic references as their $model/id pair.
    extra_dump_fields = {"product": "id,tags.id", "annotation": "id,anchor.$model,anchor.id"}
    records: dict[str, list[dict[str, Any]]] = {}

    for name, model_cls in model_classes.items():
        dumps = []

        for item in await model_cls.query.all():
            dump = await filter_selected_fields(item, None)

            if name in extra_dump_fields:
                dump = {**dump, **await filter_selected_fields(item, extra_dump_fields[name])}

            dumps.append(dump)

        records[name] = dumps

    cases = []

    for case in CASES:
        expected = await _run_case(model_classes[case["model"]], case)
        cases.append({**case, "expected_ids": expected, "ordered": bool(case.get("order_by"))})

    return {
        "metadata": {name: metadata.model_dump() for name, metadata in metadatas.items()},
        "records": records,
        "cases": cases,
    }


def _declare_extra_fields() -> None:
    from fastedgy import context
    from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType
    from fastedgy.test.models.workspace_extra_field import (
        WorkspaceExtraField,
        WorkspaceExtraFieldModel,
    )

    context.set_workspace_extra_fields(
        [
            WorkspaceExtraField(
                label="Priority",
                name="priority",
                field_type=WorkspaceExtraFieldType.integer,
                model=WorkspaceExtraFieldModel.product,
                required=False,
            ),
            WorkspaceExtraField(
                label="Owner",
                name="owner",
                field_type=WorkspaceExtraFieldType.char,
                model=WorkspaceExtraFieldModel.product,
                required=False,
            ),
        ]
    )


async def test_filter_parity(setup_db) -> None:
    from fastedgy.test.factories import use_request

    with use_request():
        _declare_extra_fields()
        parity = json.loads(json.dumps(await _build_parity(), default=str))
    output = json.dumps(parity, indent=2, ensure_ascii=False) + "\n"

    extra_out = os.environ.get("FILTER_PARITY_OUT")
    if extra_out:
        Path(extra_out).parent.mkdir(parents=True, exist_ok=True)
        Path(extra_out).write_text(output)

    if os.environ.get("REGEN_PARITY") == "1" or not PARITY_PATH.exists():
        PARITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        PARITY_PATH.write_text(output)
        return

    committed = json.loads(PARITY_PATH.read_text())

    assert committed["cases"] == parity["cases"], (
        "Query Builder semantics drifted from the committed parity fixtures — review and rerun with REGEN_PARITY=1"
    )
