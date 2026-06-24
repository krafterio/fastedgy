# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.orm.field_selector import parse_field_selector_input
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
