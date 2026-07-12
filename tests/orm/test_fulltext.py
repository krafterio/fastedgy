# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
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
    from fastedgy.orm.signals.fulltext import _handle_fulltext_save

    product = Product(name="Widget", description="A blue gadget", price="9.99")
    await product.save()

    ctid_before = await _fetch_col(product.id, "ctid::text")

    product.name = "Sprocket"
    await _handle_fulltext_save(product)

    assert await _fetch_col(product.id, "ctid::text") != ctid_before
    assert "sprocket" in await _fetch_col(product.id, "search_value_en::text")
