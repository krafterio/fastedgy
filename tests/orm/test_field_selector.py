# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.orm.field_selector import filter_selected_fields, parse_field_selector_input
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product


async def test_parse_includes_id_and_named_field(setup_db: FastEdgy) -> None:
    assert parse_field_selector_input(Product, "name") == {"id": True, "name": True}


async def test_parse_expands_nested_relation(setup_db: FastEdgy) -> None:
    assert parse_field_selector_input(Product, "name,category.name") == {
        "id": True,
        "name": True,
        "category": {"id": True, "name": True},
    }


async def test_parse_none_returns_none(setup_db: FastEdgy) -> None:
    assert parse_field_selector_input(Product, None) is None


async def test_parse_drops_excluded_scalar_field(setup_db: FastEdgy) -> None:
    """An excluded field must never enter the selector, even by explicit path —
    the excluded column is a storage/secret detail (e.g. a password)."""
    assert parse_field_selector_input(Product, "name,secret_code") == {"id": True, "name": True}


async def test_parse_drops_excluded_field_through_relation(setup_db: FastEdgy) -> None:
    assert parse_field_selector_input(Category, "name,products.secret_code") == {
        "id": True,
        "name": True,
        "products": [{"id": True}],
    }


async def test_serialize_never_leaks_excluded_scalar(setup_db: FastEdgy) -> None:
    product = await Product.query.create(name="Widget", price="9.99", secret_code="TOP-SECRET")

    direct = await filter_selected_fields(product, "name,secret_code")
    assert direct == {"id": product.id, "name": "Widget"}


async def test_serialize_never_leaks_excluded_scalar_through_relation(setup_db: FastEdgy) -> None:
    category = await Category.query.create(name="Tools")
    await Product.query.create(name="Widget", price="9.99", secret_code="TOP-SECRET", category=category)

    dump = await filter_selected_fields(category, "name,products.name,products.secret_code")
    assert dump["products"] == [{"id": dump["products"][0]["id"], "name": "Widget"}]
    assert "secret_code" not in dump["products"][0]
