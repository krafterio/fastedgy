# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Two readings of a filter over a relation that fans out.

``A & B`` is the intersection of A and B: each rule gets its own correlated
EXISTS, so its meaning does not depend on its neighbours. That matters beyond
taste, because an access rule is ANDed with whatever filter the caller wrote:
merging them would make the rule mean something else depending on the client.

``any`` is the other reading, said out loud: one related record satisfying a
whole sub-filter. ``not any`` is its negation, which a record carrying nothing
related satisfies.
"""

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import And, InvalidFilterError, Or, R, filter_query
from fastedgy.test.models.annotation import Annotation
from fastedgy.test.models.category import Category
from fastedgy.test.models.fs_optimize import FsoCategory, FsoProduct, FsoTag
from fastedgy.test.models.product import Product


async def _seed() -> None:
    """Two categories that only a same-record reading tells apart.

    `Split` holds the two values across two products, `Together` holds both on
    one. `Twice` holds both on each of two products, `Empty` holds nothing.
    """
    split = await FsoCategory(name="Split").save()
    together = await FsoCategory(name="Together").save()
    twice = await FsoCategory(name="Twice").save()
    await FsoCategory(name="Empty").save()

    await FsoProduct(name="split_price", price=100.0, quantity=1, category=split).save()
    await FsoProduct(name="split_quantity", price=50.0, quantity=5, category=split).save()

    await FsoProduct(name="together", price=100.0, quantity=5, category=together).save()

    await FsoProduct(name="twice_a", price=100.0, quantity=5, category=twice).save()
    await FsoProduct(name="twice_b", price=100.0, quantity=5, category=twice).save()


async def _categories(rule, order_by: str | None = None, **kwargs) -> list[str]:
    query = filter_query(FsoCategory.query, rule, **kwargs)

    if order_by:
        query = query.order_by(order_by)

    return [row.name for row in await query.all()]


PAIR = And(R("products.price", "=", 100.0), R("products.quantity", "=", 5))
SAME = R("products", "any", And(R("price", "=", 100.0), R("quantity", "=", 5)))


async def test_anded_rules_are_the_intersection_of_their_rules(setup_db: FastEdgy) -> None:
    await _seed()

    # `Split` has both values, on two different products: each rule reaches it,
    # so their conjunction does too.
    assert sorted(await _categories(PAIR)) == ["Split", "Together", "Twice"]

    prices = await _categories(R("products.price", "=", 100.0))
    quantities = await _categories(R("products.quantity", "=", 5))

    assert sorted(await _categories(PAIR)) == sorted(set(prices) & set(quantities))


async def test_any_asks_the_same_related_record(setup_db: FastEdgy) -> None:
    await _seed()

    # The other reading, and the contrast with the pair above: `Split` never
    # holds the two values on one product.
    assert sorted(await _categories(SAME)) == ["Together", "Twice"]


async def test_a_neighbour_rule_does_not_change_what_a_rule_accepts(setup_db: FastEdgy) -> None:
    """What disqualified the merge: an access rule is ANDed with the caller's
    filter, so a rule whose meaning shifts with its neighbours stops meaning
    what it says."""
    await _seed()

    access_rule = R("products.price", "=", 100.0)
    alone = set(await _categories(access_rule))

    for neighbour in (
        R("products.quantity", "=", 5),
        R("products.name", "=", "split_quantity"),
        R("name", "!=", "zzz"),
    ):
        together = set(await _categories(And(access_rule, neighbour)))

        assert together <= alone
        assert together == alone & set(await _categories(neighbour))


async def test_the_record_comes_back_once(setup_db: FastEdgy) -> None:
    await _seed()

    # `Twice` satisfies the sub-filter on two of its products.
    assert (await _categories(SAME)).count("Twice") == 1


async def test_a_relation_filter_leaves_no_dedup_behind(setup_db: FastEdgy) -> None:
    """An EXISTS tests the outer row instead of joining rows onto it, so there
    is nothing to dedupe: `count()` counts records, not join rows."""
    await _seed()

    for rule in (PAIR, SAME, R("products.price", "=", 100.0)):
        query = filter_query(FsoCategory.query, rule)

        assert query.distinct_on is None
        assert await query.count() == len([row.id for row in await query.all()])


@pytest.mark.parametrize("order_by", ["name", "-name"])
async def test_a_relation_filter_orders_on_any_column(setup_db: FastEdgy, order_by: str) -> None:
    """The regression a `DISTINCT ON (id)` used to cause: PostgreSQL refuses an
    ORDER BY that does not lead with the DISTINCT ON expressions, so this raised
    `InvalidColumnReferenceError` instead of returning rows."""
    await _seed()

    names = await _categories(SAME, order_by=order_by)

    assert names == (["Together", "Twice"] if order_by == "name" else ["Twice", "Together"])


async def test_ordering_on_the_filtered_relation_stays_an_aggregate(setup_db: FastEdgy) -> None:
    """Ordering by a fanning-out relation ranks a record by an aggregate of the
    far side. It only works with no dedup in the way, and it keeps one row per
    record."""
    await _seed()

    names = await _categories(R("products.price", "=", 100.0), order_by="products.price")

    # `Split` ranks on its cheapest product, 50, ahead of the two others at 100.
    assert names[0] == "Split"
    assert sorted(names) == ["Split", "Together", "Twice"]
    assert await filter_query(FsoCategory.query, R("products.price", "=", 100.0)).count() == 3


async def test_not_any_negates_the_sub_filter(setup_db: FastEdgy) -> None:
    await _seed()

    names = sorted(await _categories(R("products", "not any", R("price", "=", 100.0))))

    # `Empty` carries no product at all, which is a way of carrying none priced
    # at 100.
    assert names == ["Empty"]

    with_one = sorted(await _categories(R("products", "any", R("price", "=", 100.0))))

    assert sorted(names + with_one) == sorted(await _categories(R("name", "!=", "zzz")))


async def test_an_empty_sub_filter_asks_what_the_relation_carries(setup_db: FastEdgy) -> None:
    await _seed()

    assert sorted(await _categories(R("products", "any", None))) == ["Split", "Together", "Twice"]
    assert sorted(await _categories(R("products", "not any", None))) == ["Empty"]

    # The short forms a foreign key already had say the same thing.
    await FsoProduct(name="orphan", price=1.0).save()

    async def _products(rule) -> list[str]:
        return sorted(row.name for row in await filter_query(FsoProduct.query, rule).all())

    assert await _products(R("category", "any", None)) == await _products(R("category", "is not empty"))
    assert await _products(R("category", "not any", None)) == await _products(R("category", "is empty")) == ["orphan"]


async def test_a_sub_filter_refuses_a_field_the_caller_cannot_read(setup_db: FastEdgy) -> None:
    """The descent into the sub-filter is what checks its fields. Without it a
    caller reads an excluded column by bisecting on it, one filter at a time."""
    await _seed()

    hidden = R("products", "any", R("internal_note", "=", "secret"))

    with pytest.raises(InvalidFilterError):
        filter_query(FsoCategory.query, hidden)

    with pytest.raises(InvalidFilterError):
        filter_query(FsoCategory.query, And(R("name", "!=", "zzz"), Or(hidden, R("name", "=", "Empty"))))

    with pytest.raises(InvalidFilterError):
        filter_query(FsoCategory.query, R("products", "any", R("unknown_column", "=", 1)))

    # The refusal is the exclusion, nothing else: the system reads it fine.
    assert filter_query(FsoCategory.query, hidden, allow_excluded=True) is not None


async def test_a_sub_filter_takes_a_raw_payload(setup_db: FastEdgy) -> None:
    await _seed()

    rule = R("products", "any", ["&", [["price", "=", 100.0], ["quantity", "=", 5]]])

    assert sorted(await _categories(rule)) == ["Together", "Twice"]

    with pytest.raises(InvalidFilterError):
        filter_query(FsoCategory.query, R("products", "any", ["internal_note", "=", "secret"]))


async def test_a_sub_filter_compares_a_foreign_key_on_its_key(setup_db: FastEdgy) -> None:
    await _seed()

    together = await FsoCategory.query.filter(R("name", "=", "Together")).get()
    await FsoProduct(name="orphan", price=100.0).save()

    names = sorted(
        row.name for row in await filter_query(FsoProduct.query, R("category", "any", R("id", "=", together.id))).all()
    )

    assert names == ["together"]
    assert sorted(await _categories(R("products", "any", R("category", "=", together.id)))) == ["Together"]
    assert "Together" not in await _categories(R("products", "any", R("category", "is empty")))


async def test_any_needs_a_relation(setup_db: FastEdgy) -> None:
    await _seed()

    with pytest.raises(InvalidFilterError):
        filter_query(FsoCategory.query, R("name", "any", R("name", "=", "x")))


async def test_a_sub_filter_crosses_relations_of_its_own(setup_db: FastEdgy) -> None:
    """A path inside a sub-filter compiles like one outside it: its own nested
    EXISTS, so ANDed sub-rules stay an intersection one hop down, and a nested
    `any` says "the same one" again."""
    await _seed()

    red = await FsoTag(name="hot", color="red").save()
    blue = await FsoTag(name="cold", color="blue").save()

    together = await FsoProduct.query.filter(R("name", "=", "together")).get()
    await together.tags.add(red)

    split = await FsoProduct.query.filter(R("name", "=", "split_price")).get()
    await split.tags.add(blue)
    await split.tags.add(await FsoTag(name="warm", color="red").save())

    reached = R("products", "any", And(R("tags.color", "=", "red"), R("tags.name", "=", "hot")))
    same_tag = R("products", "any", R("tags", "any", And(R("color", "=", "red"), R("name", "=", "hot"))))

    assert sorted(await _categories(reached)) == ["Together"]
    assert sorted(await _categories(same_tag)) == ["Together"]

    # `Split` carries "red" and "cold" on two different tags: the intersection
    # reaches it, the same-tag reading does not.
    apart = And(R("tags.color", "=", "red"), R("tags.name", "=", "cold"))
    products = [row.name for row in await filter_query(FsoProduct.query, apart).all()]

    assert products == ["split_price"]
    assert [
        row.name
        for row in await filter_query(
            FsoProduct.query, R("tags", "any", And(R("color", "=", "red"), R("name", "=", "cold")))
        ).all()
    ] == []


async def test_any_over_a_generic_reverse_relation(setup_db: FastEdgy) -> None:
    """The reverse side of a generic reference names one model, so a sub-filter
    resolves against it. The reference field itself names none, and is refused."""
    electronics = await Category(name="Electronics").save()
    await Category(name="Books").save()
    laptop = await Product(name="Laptop", price=10, category=electronics).save()
    await Product(name="Novel", price=20, category=electronics).save()

    await Annotation(body="Fragile item", anchor=laptop).save()
    await Annotation(body="Category note", anchor=electronics).save()

    names = [
        row.name
        for row in await filter_query(Product.query, R("annotations", "any", R("body", "icontains", "fragile"))).all()
    ]

    assert names == ["Laptop"]

    with pytest.raises(InvalidFilterError):
        filter_query(Annotation.query, R("anchor", "any", R("name", "=", "Laptop")))


async def test_a_sub_filter_on_a_self_referencing_path(setup_db: FastEdgy) -> None:
    """The related table is the outer one: the subquery has to alias it apart,
    or the correlation compares a row to itself and stops filtering."""
    await _seed()

    parent = await FsoCategory.query.filter(R("name", "=", "Split")).get()
    child = await FsoCategory.query.filter(R("name", "=", "Empty")).get()

    child.summary = "child"
    await child.save()

    product = await FsoProduct.query.filter(R("name", "=", "split_price")).get()
    product.category = child
    await product.save()

    names = sorted(await _categories(R("products", "any", R("category.summary", "=", "child"))))

    assert names == [child.name]
    assert parent.name not in names
