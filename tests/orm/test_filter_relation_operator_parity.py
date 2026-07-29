# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Operator semantics on relation paths, bare rule versus nested condition.

A bare rule is delegated to the ORM lookups (outer joins), while the same rule
inside an OR/AND is compiled into an EXISTS subquery. The two must agree for
every operator.

They naturally do for value operators: when a hop is missing the joined columns
are NULL, the predicate evaluates to UNKNOWN and the row drops out — exactly
what an EXISTS returning false does. `is empty` is the one predicate that is
TRUE when there is nothing at the end of the path, so it is the only one an
EXISTS cannot express on its own; it is compiled as a negated existence.

Expected sets are pinned explicitly so a semantic drift fails loudly instead of
silently agreeing on an empty result.
"""

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import Or, R, filter_query
from fastedgy.test.models.fs_optimize import FsoBrand, FsoCategory, FsoProduct, FsoTag


async def _seed() -> None:
    """p_alpha: full chain (category → brand with motto, tagged)
    p_beta:   category without summary → brand without motto
    p_gamma:  category without brand
    p_orphan: no category at all"""
    acme = await FsoBrand(name="Acme", motto="Always sharp", rank=5).save()
    globex = await FsoBrand(name="Globex", rank=1).save()

    alpha = await FsoCategory(name="Alpha", summary="alpha summary", brand=acme).save()
    beta = await FsoCategory(name="Beta", brand=globex).save()
    gamma = await FsoCategory(name="Gamma", summary="gamma summary").save()

    hot = await FsoTag(name="hot").save()

    p_alpha = await FsoProduct(name="p_alpha", sku="SKU-1", price=100.0, quantity=5, category=alpha).save()
    await FsoProduct(name="p_beta", price=50.0, quantity=0, category=beta).save()
    await FsoProduct(name="p_gamma", sku="SKU-3", price=10.0, quantity=2, category=gamma).save()
    await FsoProduct(name="p_orphan", price=1.0, quantity=0).save()

    await p_alpha.tags.add(hot)


async def _names(rule) -> set[str]:
    return {row.name for row in await filter_query(FsoProduct.query, rule, allow_excluded=True).all()}


VALUE_OPERATORS = [
    ("hop1 =", R("category.name", "=", "Alpha"), {"p_alpha"}),
    ("hop1 !=", R("category.name", "!=", "Alpha"), {"p_beta", "p_gamma"}),
    ("hop1 like", R("category.name", "like", "Al%"), {"p_alpha"}),
    ("hop1 not like", R("category.name", "not like", "Al%"), {"p_beta", "p_gamma"}),
    ("hop1 ilike", R("category.name", "ilike", "al%"), {"p_alpha"}),
    ("hop1 not ilike", R("category.name", "not ilike", "al%"), {"p_beta", "p_gamma"}),
    ("hop1 contains", R("category.name", "contains", "lph"), {"p_alpha"}),
    ("hop1 not contains", R("category.name", "not contains", "lph"), {"p_beta", "p_gamma"}),
    ("hop1 icontains", R("category.name", "icontains", "LPH"), {"p_alpha"}),
    ("hop1 not icontains", R("category.name", "not icontains", "LPH"), {"p_beta", "p_gamma"}),
    ("hop1 starts with", R("category.name", "starts with", "Al"), {"p_alpha"}),
    ("hop1 not starts with", R("category.name", "not starts with", "Al"), {"p_beta", "p_gamma"}),
    ("hop1 ends with", R("category.name", "ends with", "ha"), {"p_alpha"}),
    ("hop1 not ends with", R("category.name", "not ends with", "ha"), {"p_beta", "p_gamma"}),
    ("hop1 in", R("category.name", "in", ["Alpha", "Beta"]), {"p_alpha", "p_beta"}),
    ("hop1 not in", R("category.name", "not in", ["Alpha", "Beta"]), {"p_gamma"}),
    ("hop2 =", R("category.brand.name", "=", "Acme"), {"p_alpha"}),
    ("hop2 !=", R("category.brand.name", "!=", "Acme"), {"p_beta"}),
    ("hop2 not in", R("category.brand.name", "not in", ["Acme"]), {"p_beta"}),
    ("hop2 >", R("category.brand.rank", ">", 1), {"p_alpha"}),
    ("hop2 <=", R("category.brand.rank", "<=", 1), {"p_beta"}),
    ("hop2 between", R("category.brand.rank", "between", [0, 3]), {"p_beta"}),
    ("m2m =", R("tags.name", "=", "hot"), {"p_alpha"}),
]

NULLABILITY_OPERATORS = [
    # A missing hop means "nothing at the end of the path": those rows match.
    ("hop1 col is empty", R("category.summary", "is empty"), {"p_beta", "p_orphan"}),
    ("hop1 col is not empty", R("category.summary", "is not empty"), {"p_alpha", "p_gamma"}),
    ("hop2 col is empty", R("category.brand.motto", "is empty"), {"p_beta", "p_gamma", "p_orphan"}),
    ("hop2 col is not empty", R("category.brand.motto", "is not empty"), {"p_alpha"}),
    ("hop2 relation is empty", R("category.brand", "is empty"), {"p_gamma", "p_orphan"}),
    ("hop2 relation is not empty", R("category.brand", "is not empty"), {"p_alpha", "p_beta"}),
    ("m2m col is empty", R("tags.color", "is empty"), {"p_alpha", "p_beta", "p_gamma", "p_orphan"}),
]


@pytest.mark.parametrize("label, rule, expected", VALUE_OPERATORS, ids=lambda v: v if isinstance(v, str) else "")
async def test_value_operators_agree_bare_and_nested(setup_db: FastEdgy, label, rule, expected) -> None:
    await _seed()

    assert await _names(rule) == expected
    assert await _names(Or(rule)) == expected


@pytest.mark.parametrize("label, rule, expected", NULLABILITY_OPERATORS, ids=lambda v: v if isinstance(v, str) else "")
async def test_nullability_operators_agree_bare_and_nested(setup_db: FastEdgy, label, rule, expected) -> None:
    await _seed()

    assert await _names(rule) == expected
    assert await _names(Or(rule)) == expected
