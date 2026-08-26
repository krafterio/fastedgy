# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Query Builder rules passed straight to `filter()`.

`Model.query.filter(R(...))` has to mean exactly what `filter_query(Model.query,
R(...))` means, including the parts a plain ORM lookup does not do: validating
the field and the operator, resolving a relation path, and deduping the joins a
to-many rule would otherwise repeat.

The ORM's own forms must keep working next to it, since `filter()` stays the one
entry point: keyword lookups, SQLAlchemy clauses, and any mix of the three.
"""

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import And, InvalidFilterError, Or, R, filter_query
from fastedgy.test.models.fs_optimize import FsoBrand, FsoCategory, FsoProduct, FsoTag


async def _seed() -> None:
    acme = await FsoBrand(name="Acme", motto="Always sharp", rank=5).save()
    globex = await FsoBrand(name="Globex", rank=1).save()

    alpha = await FsoCategory(name="Alpha", summary="alpha summary", brand=acme).save()
    beta = await FsoCategory(name="Beta", brand=globex).save()

    hot = await FsoTag(name="hot").save()
    cold = await FsoTag(name="cold").save()

    p_alpha = await FsoProduct(name="p_alpha", sku="SKU-1", price=100.0, quantity=5, category=alpha).save()
    await FsoProduct(name="p_beta", price=50.0, quantity=0, category=beta).save()
    await FsoProduct(name="p_orphan", price=1.0, quantity=0).save()

    # Two tags on one product: a to-many rule joins it twice without dedup.
    await p_alpha.tags.add(hot)
    await p_alpha.tags.add(cold)


RULES = [
    ("rule", R("name", "=", "p_alpha")),
    ("relation path", R("category.name", "=", "Alpha")),
    ("two hops", R("category.brand.name", "=", "Acme")),
    ("null check", R("category.summary", "is not empty")),
    ("and", And(R("price", ">", 10), R("quantity", ">", 0))),
    ("or", Or(R("name", "=", "p_alpha"), R("name", "=", "p_beta"))),
    ("to-many", R("tags.name", "in", ["hot", "cold"])),
]


@pytest.mark.parametrize("label, rule", RULES, ids=lambda v: v if isinstance(v, str) else "")
async def test_filter_matches_filter_query(setup_db: FastEdgy, label, rule) -> None:
    await _seed()

    through_filter = [row.name for row in await FsoProduct.query.filter(rule).all()]
    through_helper = [row.name for row in await filter_query(FsoProduct.query, rule).all()]

    assert through_filter == through_helper
    assert through_filter, f"{label} matched nothing, so the comparison proves nothing"


async def test_a_to_many_rule_does_not_repeat_the_row(setup_db: FastEdgy) -> None:
    """The dedup `filter_query` installs has to survive the `filter()` route."""
    await _seed()

    names = [row.name for row in await FsoProduct.query.filter(R("tags.name", "in", ["hot", "cold"])).all()]

    assert names == ["p_alpha"]


async def test_keyword_lookups_still_work(setup_db: FastEdgy) -> None:
    await _seed()

    names = {row.name for row in await FsoProduct.query.filter(name="p_beta").all()}

    assert names == {"p_beta"}


async def test_a_rule_combines_with_keyword_lookups(setup_db: FastEdgy) -> None:
    await _seed()

    names = {row.name for row in await FsoProduct.query.filter(R("price", ">", 10), quantity=5).all()}

    assert names == {"p_alpha"}


async def test_several_rules_are_combined_with_and(setup_db: FastEdgy) -> None:
    await _seed()

    names = {row.name for row in await FsoProduct.query.filter(R("price", ">", 10), R("quantity", ">", 0)).all()}

    assert names == {"p_alpha"}


async def test_a_sqlalchemy_clause_still_works_beside_a_rule(setup_db: FastEdgy) -> None:
    await _seed()

    query = FsoProduct.query.filter(R("price", ">", 10), FsoProduct.table.c.quantity > 0)

    assert {row.name for row in await query.all()} == {"p_alpha"}


async def test_an_unknown_field_is_refused(setup_db: FastEdgy) -> None:
    """The validation is the point of routing through the builder at all."""
    await _seed()

    with pytest.raises(InvalidFilterError):
        await FsoProduct.query.filter(R("nonexistent", "=", 1)).all()


async def test_filter_stays_chainable(setup_db: FastEdgy) -> None:
    await _seed()

    query = FsoProduct.query.filter(R("price", ">", 10)).filter(R("quantity", ">", 0))

    assert {row.name for row in await query.all()} == {"p_alpha"}


async def test_an_unparsed_filter_payload_is_routed_through_the_builder(setup_db: FastEdgy) -> None:
    """A route may hand its `X-Filter` header straight to `filter()`.

    The ORM reads a bare string as textual SQL, so the JSON has to be recognised
    as a filter here rather than fall through and raise at build time.
    """
    await _seed()

    payload = '[["price", ">", 10]]'

    assert {row.name for row in await FsoProduct.query.filter(payload).all()} == {"p_alpha", "p_beta"}
    assert {row.name for row in await FsoProduct.query.filter([["price", ">", 10]]).all()} == {"p_alpha", "p_beta"}


async def test_an_unparsed_filter_payload_is_validated(setup_db: FastEdgy) -> None:
    await _seed()

    with pytest.raises(InvalidFilterError):
        await FsoProduct.query.filter('[["nonexistent", "=", 1]]').all()


async def test_a_foreign_key_rule_compiles_without_a_join(setup_db: FastEdgy) -> None:
    """A foreign key already holds the target's key.

    Comparing it used to append that key and fall back to an ORM lookup, which
    joins the target and reads the source table through it. On a large table
    under SERIALIZABLE that costs a predicate lock per page read, and the local
    column carries the same value.
    """
    await _seed()

    category = await FsoCategory.query.filter(R("name", "=", "Alpha")).get()
    sql = str(await FsoProduct.query.filter(R("category", "=", category.id)).as_select())

    assert "JOIN" not in sql.upper()
    assert {row.name for row in await FsoProduct.query.filter(R("category", "=", category.id)).all()} == {"p_alpha"}


async def test_a_foreign_key_rule_keeps_the_other_operators(setup_db: FastEdgy) -> None:
    await _seed()

    alpha = await FsoCategory.query.filter(R("name", "=", "Alpha")).get()
    beta = await FsoCategory.query.filter(R("name", "=", "Beta")).get()

    async def names(rule):
        return {row.name for row in await FsoProduct.query.filter(rule).all()}

    assert await names(R("category", "in", [alpha.id, beta.id])) == {"p_alpha", "p_beta"}
    assert await names(R("category", "!=", alpha.id)) == {"p_beta"}
    assert await names(R("category", "is empty")) == {"p_orphan"}
    assert await names(R("category", "is not empty")) == {"p_alpha", "p_beta"}


async def test_a_foreign_key_rule_refuses_a_record(setup_db: FastEdgy) -> None:
    """The rule carries the key the column holds, so a record is refused here.

    Left to the driver it would only fail once the query runs, as a type error
    on the bound parameter.
    """
    await _seed()

    category = await FsoCategory.query.filter(R("name", "=", "Alpha")).get()

    with pytest.raises(InvalidFilterError):
        await FsoProduct.query.filter(R("category", "=", category)).all()

    with pytest.raises(InvalidFilterError):
        await FsoProduct.query.filter(R("category", "in", [category])).all()
