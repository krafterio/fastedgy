# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.orm.filter import filter_query
from fastedgy.orm.order_by import inject_order_by
from fastedgy.test.factories import create_product
from fastedgy.test.models.product import Product


async def test_fulltext_column_is_populated_on_save(setup_db: FastEdgy) -> None:
    product = Product(name="Widget", description="A blue gadget", price="9.99")
    await product.save()

    database = get_service(Registry).database
    row = await database.fetch_one(
        "SELECT search_value_en FROM test_products WHERE id = :id",
        {"id": product.id},
    )

    assert row is not None

    indexed = str(row[0])

    assert "widget" in indexed
    assert "gadget" in indexed


async def _fetch_col(product_id: int | None, col: str) -> str:
    database = get_service(Registry).database
    row = await database.fetch_one(
        f"SELECT {col} FROM test_products WHERE id = :id",
        {"id": product_id},
    )

    assert row is not None

    return str(row[0])


async def test_fulltext_unchanged_source_writes_nothing(setup_db: FastEdgy) -> None:
    from fastedgy.orm.signals.fulltext import _handle_fulltext_save

    product = Product(name="Widget", description="A blue gadget", price="9.99")
    await product.save()

    ctid_before = await _fetch_col(product.id, "ctid::text")
    tsv_before = await _fetch_col(product.id, "search_value_en::text")

    await _handle_fulltext_save(product)

    assert await _fetch_col(product.id, "ctid::text") == ctid_before
    assert await _fetch_col(product.id, "search_value_en::text") == tsv_before


async def test_fulltext_changed_source_still_recomputes(setup_db: FastEdgy) -> None:
    product = Product(name="Widget", description="A blue gadget", price="9.99")
    await product.save()

    product.name = "Sprocket"
    await product.save()

    assert "sprocket" in await _fetch_col(product.id, "search_value_en::text")


async def test_fulltext_partial_save_keeps_the_fields_it_never_loaded(setup_db: FastEdgy) -> None:
    # The vector is computed from the table, not from the instance. An instance
    # carrying only the field it changes used to rebuild the vector out of what
    # it happened to hold, dropping every word from a column it never read. The
    # next full save put them back, so the record flip-flopped between two
    # vectors and rewrote the GIN index on every single save.
    product = Product(name="Widget", description="A blue gadget", price="9.99")
    await product.save()

    lean = Product(id=product.id, name="Sprocket", price="9.99")
    await lean.save(values={"name": "Sprocket"})

    indexed = await _fetch_col(product.id, "search_value_en::text")

    assert "sprocket" in indexed
    assert "gadget" in indexed


async def test_fulltext_skips_an_update_touching_no_searchable_field(setup_db: FastEdgy) -> None:
    # Nothing indexed changed, so the statement must not run at all. A stored
    # vector that no longer matches the row is the only way to observe it: the
    # IS DISTINCT FROM guard would hide a skip from a ctid comparison.
    product = Product(name="Widget", description="A blue gadget", price="9.99")
    await product.save()

    database = get_service(Registry).database
    await database.execute(
        "UPDATE test_products SET search_value_en = to_tsvector('simple', 'stale') WHERE id = :id",
        {"id": product.id},
    )

    product.quantity = 5
    await product.save(values={"quantity": 5})

    assert "stale" in await _fetch_col(product.id, "search_value_en::text")


async def test_order_by_search_relevance(setup_db: FastEdgy) -> None:
    # The filter labels a rank expression in extra_select; ordering by the
    # fulltext field sorts on that label, not on the stored search column.
    await create_product(name="Laptop Pro", price="10.00")
    await create_product(name="Novel", price="5.00")

    query = filter_query(Product.query.get_queryset(), json.dumps(["search_value", "search", "laptop"]))
    items = await inject_order_by(query, "search_value:desc").all()

    assert [item.name for item in items] == ["Laptop Pro"]


def test_view_backed_models_are_left_alone() -> None:
    # A view computes its tsvector in its own SELECT, and PostgreSQL refuses to
    # update one that returns a window function. Both the reindex command and
    # the save signal read the flag off Meta, not off meta.
    from fastedgy.models.base import BaseView
    from fastedgy.orm.fields.field_fulltext import is_view_model

    class NotAView:
        class Meta:
            tablename = "products"

    class AView(BaseView):
        class Meta(BaseView.Meta):
            tablename = "candidates"

    class ABareMetaView(BaseView):
        # A view is free to declare its own Meta from scratch, and then it
        # inherits no is_view at all. The class still says what it is.
        class Meta:
            tablename = "bare_candidates"

    class AFlaggedModel:
        class Meta:
            tablename = "flagged"
            is_view = True

    assert is_view_model(AView)
    assert is_view_model(ABareMetaView)
    assert is_view_model(AFlaggedModel)
    assert not is_view_model(NotAView)
