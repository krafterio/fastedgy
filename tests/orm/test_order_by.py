# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.orm.order_by import parse_order_by
from fastedgy.test.models.product import Product


async def test_parse_directions_default_to_asc(setup_db: FastEdgy) -> None:
    assert parse_order_by(Product, "name:desc,price") == [("name", "desc"), ("price", "asc")]


async def test_parse_none_returns_empty_list(setup_db: FastEdgy) -> None:
    assert parse_order_by(Product, None) == []
