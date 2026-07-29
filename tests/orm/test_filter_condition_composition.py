# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Boolean algebra of nested filter conditions.

A rule standing alone is delegated to the ORM lookups, while the same rule
inside an OR/AND is compiled into an EXISTS subquery so each branch keeps its
own JOIN context. Both compilations must agree, and nesting conditions must
behave like the matching set operation — whatever the depth of the relation
path involved (direct column, one hop, two hops, many-to-many).

These tests pin that algebra: every composition is checked against the set
expression built from the atomic results.
"""

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import And, Or, R, filter_query
from fastedgy.test.models.fs_optimize import FsoBrand, FsoCategory, FsoProduct, FsoTag


async def _seed() -> None:
    acme = await FsoBrand(name="Acme", motto="Always sharp", rank=5).save()
    globex = await FsoBrand(name="Globex", rank=1).save()

    alpha = await FsoCategory(name="Alpha", summary="alpha summary", brand=acme).save()
    beta = await FsoCategory(name="Beta", brand=globex).save()
    gamma = await FsoCategory(name="Gamma", summary="gamma summary").save()

    hot = await FsoTag(name="hot").save()
    cold = await FsoTag(name="cold").save()

    p_alpha = await FsoProduct(name="p_alpha", sku="SKU-1", price=100.0, quantity=5, category=alpha).save()
    p_beta = await FsoProduct(name="p_beta", price=50.0, quantity=0, category=beta).save()
    p_gamma = await FsoProduct(name="p_gamma", sku="SKU-3", price=10.0, quantity=2, category=gamma).save()
    await FsoProduct(name="p_orphan", price=1.0, quantity=0).save()
    await FsoProduct(name="p_alpha_bis", sku="SKU-5", price=100.0, quantity=1, category=alpha).save()

    await p_alpha.tags.add(hot)
    await p_beta.tags.add(hot)
    await p_beta.tags.add(cold)
    await p_gamma.tags.add(cold)


async def _names(rule) -> set[str]:
    return {row.name for row in await filter_query(FsoProduct.query, rule, allow_excluded=True).all()}


# Atomic rules spanning every path shape: direct column, nullable direct column,
# one hop, two hops, nullability at each depth, many-to-many and a numeric
# comparison at the deepest level.
ATOMS = {
    "direct_eq": R("price", "=", 100.0),
    "direct_null": R("sku", "is empty"),
    "hop1_eq": R("category.name", "=", "Alpha"),
    "hop1_null": R("category.summary", "is empty"),
    "hop1_rel_null": R("category", "is empty"),
    "hop2_eq": R("category.brand.name", "=", "Acme"),
    "hop2_null": R("category.brand.motto", "is empty"),
    "hop2_rel_null": R("category.brand", "is empty"),
    "hop2_gt": R("category.brand.rank", ">", 1),
    "m2m_eq": R("tags.name", "=", "hot"),
    "m2m_null": R("tags.color", "is empty"),
}

TRIPLETS = [
    ("direct_eq", "hop1_eq", "hop2_eq"),
    ("hop2_rel_null", "hop2_eq", "direct_null"),
    ("hop1_rel_null", "hop1_null", "hop2_null"),
    ("m2m_eq", "hop2_gt", "hop1_eq"),
    ("hop2_null", "m2m_eq", "hop1_rel_null"),
    ("direct_null", "m2m_null", "hop2_rel_null"),
]

# (label, rule builder, expected set builder) — two and three levels of nesting.
COMPOSITIONS = [
    ("or(a,b)", lambda a, b, c: Or(a, b), lambda A, B, C: A | B),
    ("and(a,b)", lambda a, b, c: And(a, b), lambda A, B, C: A & B),
    ("or(a,b,c)", lambda a, b, c: Or(a, b, c), lambda A, B, C: A | B | C),
    ("and(a,b,c)", lambda a, b, c: And(a, b, c), lambda A, B, C: A & B & C),
    ("or(a,and(b,c))", lambda a, b, c: Or(a, And(b, c)), lambda A, B, C: A | (B & C)),
    ("and(a,or(b,c))", lambda a, b, c: And(a, Or(b, c)), lambda A, B, C: A & (B | C)),
    ("or(and(a,b),and(a,c))", lambda a, b, c: Or(And(a, b), And(a, c)), lambda A, B, C: (A & B) | (A & C)),
    ("and(or(a,b),or(a,c))", lambda a, b, c: And(Or(a, b), Or(a, c)), lambda A, B, C: (A | B) & (A | C)),
    ("or(a,and(b,or(a,c)))", lambda a, b, c: Or(a, And(b, Or(a, c))), lambda A, B, C: A | (B & (A | C))),
    ("and(a,or(b,and(a,c)))", lambda a, b, c: And(a, Or(b, And(a, c))), lambda A, B, C: A & (B | (A & C))),
    (
        "or(and(a,or(b,c)),and(c,or(a,b)))",
        lambda a, b, c: Or(And(a, Or(b, c)), And(c, Or(a, b))),
        lambda A, B, C: (A & (B | C)) | (C & (A | B)),
    ),
    (
        "and(or(a,and(b,c)),or(c,and(a,b)))",
        lambda a, b, c: And(Or(a, And(b, c)), Or(c, And(a, b))),
        lambda A, B, C: (A | (B & C)) & (C | (A & B)),
    ),
]


@pytest.mark.parametrize("key", list(ATOMS))
async def test_equivalent_shapes_of_a_single_rule_agree(setup_db: FastEdgy, key: str) -> None:
    """A rule alone, wrapped in a condition, or duplicated inside one, all
    describe the same predicate — this is the parity the EXISTS compilation
    must preserve."""
    await _seed()

    rule = ATOMS[key]
    expected = await _names(rule)

    assert await _names(Or(rule)) == expected
    assert await _names(And(rule)) == expected
    assert await _names(Or(rule, rule)) == expected
    assert await _names(And(rule, rule)) == expected
    assert await _names(Or(And(rule), Or(rule))) == expected


@pytest.mark.parametrize("triplet", TRIPLETS, ids=lambda t: "+".join(t))
@pytest.mark.parametrize("composition", COMPOSITIONS, ids=lambda c: c[0])
async def test_nested_conditions_follow_set_algebra(setup_db: FastEdgy, triplet, composition) -> None:
    await _seed()

    key_a, key_b, key_c = triplet
    _label, build_rule, build_expected = composition

    a, b, c = ATOMS[key_a], ATOMS[key_b], ATOMS[key_c]
    set_a, set_b, set_c = await _names(a), await _names(b), await _names(c)

    assert await _names(build_rule(a, b, c)) == build_expected(set_a, set_b, set_c)


async def test_deep_nesting_keeps_relation_branches_independent(setup_db: FastEdgy) -> None:
    """Branches touching different relation depths must not share JOIN context:
    a three-level nesting mixing a two-hop nullability escape hatch with value
    branches is the shape used by record visibility filters."""
    await _seed()

    rule = Or(
        R("category", "is empty"),
        And(
            R("category.brand", "is empty"),
            Or(R("category.name", "=", "Gamma"), R("category.summary", "is empty")),
        ),
        And(
            R("category.brand.name", "=", "Acme"),
            Or(R("category.brand.rank", ">", 1), R("tags.name", "=", "cold")),
        ),
    )

    assert await _names(rule) == {"p_orphan", "p_gamma", "p_alpha", "p_alpha_bis"}
