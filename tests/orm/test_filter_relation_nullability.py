# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Nullability filters on relation paths.

Rules living inside an OR/AND condition are compiled into EXISTS subqueries
(so each branch keeps its own JOIN context), while a bare rule is delegated to
the ORM lookups. Both paths must agree, and `is empty` on a relation leaf must
stay on the parent foreign key column: hopping to the target primary key adds a
JOIN that drops the very rows the predicate is meant to match.
"""

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import And, Or, R, filter_query
from fastedgy.test.models.fs_optimize import FsoBrand, FsoCategory, FsoProduct


async def _seed() -> None:
    brand = await FsoBrand(name="Acme").save()

    branded = await FsoCategory(name="Branded", summary="described", brand=brand).save()
    unbranded = await FsoCategory(name="Unbranded").save()

    await FsoProduct(name="with brand", category=branded).save()
    await FsoProduct(name="without brand", category=unbranded).save()
    await FsoProduct(name="without category").save()


async def _names(rule) -> set[str]:
    return {row.name for row in await filter_query(FsoProduct.query, rule, allow_excluded=True).all()}


async def test_is_empty_on_relation_leaf_matches_rows_whose_target_is_missing(setup_db: FastEdgy) -> None:
    await _seed()

    assert await _names(R("category.brand", "is empty")) == {"without brand", "without category"}


async def test_is_empty_on_a_plain_column_leaf_behaves_the_same_inside_a_condition(setup_db: FastEdgy) -> None:
    """Same parity requirement when the leaf is a plain nullable column: a row
    whose intermediate hop is missing has nothing at the end of the path."""
    await _seed()

    bare = await _names(R("category.summary", "is empty"))

    assert bare == {"without brand", "without category"}
    assert await _names(Or(R("category.summary", "is empty"))) == bare


async def test_is_empty_on_relation_leaf_behaves_the_same_inside_a_condition(setup_db: FastEdgy) -> None:
    """Regression: the EXISTS compilation used to hop to the target primary key,
    turning the predicate into `brands.id IS NULL` behind a JOIN — unsatisfiable,
    so the branch silently matched nothing."""
    await _seed()

    bare = await _names(R("category.brand", "is empty"))

    assert await _names(Or(R("category.brand", "is empty"))) == bare
    assert await _names(And(R("category.brand", "is empty"))) == bare


async def test_is_not_empty_on_relation_leaf_is_the_complement(setup_db: FastEdgy) -> None:
    await _seed()

    assert await _names(R("category.brand", "is not empty")) == {"with brand"}
    assert await _names(Or(R("category.brand", "is not empty"))) == {"with brand"}


async def test_nullability_branch_unions_with_other_branches(setup_db: FastEdgy) -> None:
    """The shape used by visibility filters: a nullability escape hatch ORed with
    value-based branches on the same relation path."""
    await _seed()

    rule = Or(
        R("category", "is empty"),
        R("category.brand", "is empty"),
        R("category.brand.name", "=", "Acme"),
    )

    assert await _names(rule) == {"with brand", "without brand", "without category"}


@pytest.mark.parametrize(
    "rule_factory, expected",
    [
        (lambda: R("category.brand.name", "=", "Acme"), {"with brand"}),
        (lambda: R("category.name", "=", "Unbranded"), {"without brand"}),
        (lambda: R("category", "is empty"), {"without category"}),
    ],
)
async def test_value_operators_and_direct_columns_are_unchanged(setup_db: FastEdgy, rule_factory, expected) -> None:
    await _seed()

    rule = rule_factory()

    assert await _names(rule) == expected
    assert await _names(Or(rule)) == expected
