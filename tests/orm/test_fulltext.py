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
