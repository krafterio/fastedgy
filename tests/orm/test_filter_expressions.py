# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Expressions in the values of a filter, and `contains` on a JSON field.

A value between backticks is evaluated when the filter is validated, so a
stored filter keeps meaning "the last thirty days" whatever day it is read.
"""

from datetime import UTC, datetime, timedelta

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import InvalidFilterError, R, filter_query
from fastedgy.orm.filter.expressions import evaluate, resolve
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product


def test_today_moves_by_a_number_of_days() -> None:
    day = datetime.now(UTC).date()

    assert evaluate("`today()`") == day.isoformat()
    assert evaluate("`today(-30)`") == (day - timedelta(days=30)).isoformat()
    assert evaluate("today(3 * -10)") == (day - timedelta(days=30)).isoformat()


def test_now_is_an_aware_instant() -> None:
    assert datetime.fromisoformat(evaluate("`now()`")).tzinfo is not None


def test_literals_read_as_kastor_writes_them() -> None:
    assert evaluate("`[1, 'a', true, false, null]`") == [1, "a", True, False, None]


@pytest.mark.parametrize(
    "expression",
    [
        "`__import__('os')`",
        "`today.__class__`",
        "`open('x')`",
        "`today(offset=1)`",
        "`2 ** 10`",
        "`today('x')`",
        "`1 / 0`",
        "`today(`",
        "`" + "1+" * 150 + "1`",
    ],
)
def test_anything_else_is_refused(expression: str) -> None:
    with pytest.raises(InvalidFilterError):
        evaluate(expression)


def test_a_value_without_backticks_stays_as_it_is() -> None:
    assert resolve("today(-1)") == "today(-1)"
    assert resolve(["`today()`", 3]) == [datetime.now(UTC).date().isoformat(), 3]


async def _seed() -> Category:
    now = datetime.now(UTC)
    shelf = await Category(name="Shelf").save()
    await Product(
        name="recent",
        price=1,
        published_at=now - timedelta(days=2),
        released_on=now.date() - timedelta(days=2),
        details=["new", "red"],
        category=shelf,
    ).save()
    await Product(
        name="old",
        price=1,
        published_at=now - timedelta(days=90),
        released_on=now.date() - timedelta(days=90),
        details=["red"],
    ).save()

    return shelf


async def _names(rule: R) -> list[str]:
    return sorted(row.name for row in await filter_query(Product.query, rule).all())


async def test_a_relative_day_on_a_datetime(setup_db: FastEdgy) -> None:
    await _seed()

    assert await _names(R("published_at", ">=", "`today(-30)`")) == ["recent"]
    assert await _names(R("published_at", "<", "`today(-30)`")) == ["old"]


async def test_a_relative_day_on_a_date_and_in_a_range(setup_db: FastEdgy) -> None:
    await _seed()

    assert await _names(R("released_on", ">=", "`today(-30)`")) == ["recent"]
    assert await _names(R("released_on", "between", ["`today(-100)`", "`today(-60)`"])) == ["old"]


async def test_a_relative_day_in_a_sub_filter(setup_db: FastEdgy) -> None:
    await _seed()

    shelves = await filter_query(Category.query, R("products", "any", [["published_at", ">=", "`today(-30)`"]])).all()

    assert [shelf.name for shelf in shelves] == ["Shelf"]


async def test_a_bad_expression_fails_the_filter(setup_db: FastEdgy) -> None:
    with pytest.raises(InvalidFilterError):
        await _names(R("published_at", ">=", "`yesterday()`"))


async def test_a_json_array_contains_an_element(setup_db: FastEdgy) -> None:
    await _seed()

    assert await _names(R("details", "contains", "new")) == ["recent"]
    assert await _names(R("details", "contains", "red")) == ["old", "recent"]
    assert await _names(R("details", "not contains", "new")) == ["old"]
    assert await _names(R("details", "contains", ["new", "red"])) == ["recent"]


async def test_a_json_array_in_a_sub_filter(setup_db: FastEdgy) -> None:
    await _seed()

    shelves = await filter_query(Category.query, R("products", "any", [["details", "contains", "new"]])).all()

    assert [shelf.name for shelf in shelves] == ["Shelf"]
