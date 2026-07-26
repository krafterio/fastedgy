# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from decimal import Decimal

from fastedgy.app import FastEdgy
from fastedgy.orm.copy import is_copyable_field
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product
from fastedgy.test.models.tag import Tag


async def _product(**values) -> Product:
    product = Product(
        name="Original",
        description="A product",
        price=Decimal("12.50"),
        quantity=3,
        details={"color": "red"},
        **values,
    )
    await product.save()

    return product


def test_system_fields_are_not_copyable() -> None:
    for name in ("id", "created_at", "updated_at"):
        assert is_copyable_field(Product.meta.fields[name]) is False

    assert is_copyable_field(Product.meta.fields["search_value"]) is False
    assert is_copyable_field(Product.meta.fields["pk"]) is False


def test_own_fields_are_copyable() -> None:
    for name in ("name", "description", "price", "quantity", "details", "category", "tags"):
        assert is_copyable_field(Product.meta.fields[name]) is True


async def test_duplicate_persists_a_new_record_with_the_same_values(setup_db: FastEdgy) -> None:
    category = Category(name="Tools")
    await category.save()
    product = await _product(category=category)

    duplicated = await product.duplicate()

    assert duplicated.id is not None
    assert duplicated.id != product.id
    assert duplicated.name == "Original"
    assert duplicated.description == "A product"
    assert duplicated.price == Decimal("12.50")
    assert duplicated.quantity == 3
    assert duplicated.details == {"color": "red"}

    stored = await Product.query.get(id=duplicated.id)
    assert stored.name == "Original"
    assert stored.category.pk == category.pk


async def test_duplicate_applies_the_given_values_over_the_original(setup_db: FastEdgy) -> None:
    product = await _product()

    duplicated = await product.duplicate({"name": "Renamed", "quantity": 0})

    assert duplicated.name == "Renamed"
    assert duplicated.quantity == 0
    assert duplicated.description == "A product"


async def test_duplicate_recreates_the_to_many_links(setup_db: FastEdgy) -> None:
    first = Tag(name="new")
    await first.save()
    second = Tag(name="sale")
    await second.save()
    product = await _product()
    await product.tags.add(first)
    await product.tags.add(second)

    duplicated = await product.duplicate()

    assert {tag.name for tag in await duplicated.tags.all()} == {"new", "sale"}
    assert {tag.name for tag in await product.tags.all()} == {"new", "sale"}


async def test_duplicate_leaves_the_original_alone(setup_db: FastEdgy) -> None:
    product = await _product()

    await product.duplicate({"name": "Copy"})

    assert (await Product.query.get(id=product.id)).name == "Original"
    assert await Product.query.count() == 2
