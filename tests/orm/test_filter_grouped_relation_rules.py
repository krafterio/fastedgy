# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Several ANDed rules over one relation that fans out.

They mean "the same related row satisfies all of them". Keeping that meaning
used to cost a shared join, which repeats the source record once per related
row and needs a ``DISTINCT ON (pk)`` to undo. PostgreSQL then refuses any ORDER
BY that does not lead with that expression, so a list route taking `order_by`
failed at the database rather than at build time.

They are now folded into a single EXISTS carrying the conjunction: same
meaning, nothing repeated, ordering free. These tests pin both halves, the
semantics and the absence of dedup, so neither can be traded for the other.
"""

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import And, Or, R, filter_query
from fastedgy.test.models.fs_optimize import FsoCategory, FsoProduct, FsoTag


async def _seed() -> None:
    """Two categories that only a same-row reading tells apart.

    `split` holds the two values across two products, `together` holds both on
    one. A filter asking for price 100 *and* quantity 5 means `together` only.
    """
    split = await FsoCategory(name="Split").save()
    together = await FsoCategory(name="Together").save()
    twice = await FsoCategory(name="Twice").save()
    await FsoCategory(name="Empty").save()

    await FsoProduct(name="split_price", price=100.0, quantity=1, category=split).save()
    await FsoProduct(name="split_quantity", price=50.0, quantity=5, category=split).save()

    await FsoProduct(name="together", price=100.0, quantity=5, category=together).save()

    # Two products of the same category satisfying the pair: the category has
    # to come back once, which is what the join needed a DISTINCT ON for.
    await FsoProduct(name="twice_a", price=100.0, quantity=5, category=twice).save()
    await FsoProduct(name="twice_b", price=100.0, quantity=5, category=twice).save()


async def _categories(rule, order_by: str | None = None) -> list[str]:
    query = filter_query(FsoCategory.query, rule)

    if order_by:
        query = query.order_by(order_by)

    return [row.name for row in await query.all()]


PAIR = And(R("products.price", "=", 100.0), R("products.quantity", "=", 5))


async def test_anded_rules_want_the_same_related_row(setup_db: FastEdgy) -> None:
    await _seed()

    # `Split` has both values, on two different products: it must stay out.
    assert sorted(await _categories(PAIR)) == ["Together", "Twice"]

    # Taken apart, each rule does reach it. That contrast is the whole point:
    # the conjunction is not the intersection of the two.
    assert "Split" in await _categories(R("products.price", "=", 100.0))
    assert "Split" in await _categories(R("products.quantity", "=", 5))


async def test_the_record_comes_back_once(setup_db: FastEdgy) -> None:
    await _seed()

    names = await _categories(PAIR)

    # `Twice` satisfies the pair on two of its products.
    assert names.count("Twice") == 1


async def test_the_group_leaves_no_dedup_behind(setup_db: FastEdgy) -> None:
    await _seed()

    query = filter_query(FsoCategory.query, PAIR)

    assert query.distinct_on is None
    assert await query.count() == 2


@pytest.mark.parametrize("order_by", ["name", "-name"])
async def test_the_group_orders_on_any_column(setup_db: FastEdgy, order_by: str) -> None:
    """The regression: a `DISTINCT ON (id)` left behind made this raise
    `InvalidColumnReferenceError` instead of returning rows."""
    await _seed()

    names = await _categories(PAIR, order_by=order_by)

    assert names == (["Together", "Twice"] if order_by == "name" else ["Twice", "Together"])


async def test_three_rules_on_one_relation_still_mean_one_row(setup_db: FastEdgy) -> None:
    await _seed()

    rule = And(
        R("products.price", "=", 100.0),
        R("products.quantity", "=", 5),
        R("products.name", "starts with", "twice"),
    )

    assert await _categories(rule, order_by="name") == ["Twice"]


async def test_a_leaf_crossing_another_relation_joins_inside_the_subquery(setup_db: FastEdgy) -> None:
    """A group whose rules do not all stop at the same table: one names a
    column of the related record, the other a column one hop further."""
    await _seed()

    hot = await FsoTag(name="hot", color="red").save()
    cold = await FsoTag(name="cold").save()

    product = await FsoProduct.query.filter(R("name", "=", "together")).get()
    await product.tags.add(hot)

    other = await FsoProduct.query.filter(R("name", "=", "split_price")).get()
    await other.tags.add(cold)

    rule = And(R("tags.name", "=", "hot"), R("tags.color", "=", "red"))
    names = [row.name for row in await filter_query(FsoProduct.query, rule).order_by("name").all()]

    assert names == ["together"]

    # The same two values held by two different tags of one product: no single
    # tag satisfies both, so the product stays out.
    await other.tags.add(await FsoTag(name="warm", color="red").save())
    rule_split = And(R("tags.name", "=", "cold"), R("tags.color", "=", "red"))

    assert [row.name for row in await filter_query(FsoProduct.query, rule_split).all()] == []


async def test_is_empty_keeps_its_own_compilation(setup_db: FastEdgy) -> None:
    """ "is empty" over a relation means "nothing at the end of the path", which
    has to stay the negation of an EXISTS of its own. Such a group is left on
    the join, dedup included, and keeps that whole-relation reading rather than
    the same-row one."""
    await _seed()

    rule = And(R("products.price", "=", 100.0), R("products.sku", "is empty"))
    query = filter_query(FsoCategory.query, rule)

    assert query.distinct_on == ["id"]

    # No product carries a sku, so "no product has one" holds everywhere, and
    # `Split` comes back on the strength of its price-100 product alone. Folded
    # into the group it would have had to be the *same* product, and `Split`
    # would be out: that difference is why "is empty" stays on its own.
    assert sorted(row.name for row in await query.all()) == ["Split", "Together", "Twice"]


async def test_a_group_inside_an_or_keeps_its_branch(setup_db: FastEdgy) -> None:
    await _seed()

    rule = Or(PAIR, R("name", "=", "Empty"))

    assert sorted(await _categories(rule)) == ["Empty", "Together", "Twice"]
