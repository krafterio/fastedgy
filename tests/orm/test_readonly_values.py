# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""``apply_readonly_values``: the explicit code-side escape hatch to persist
``read_only`` fields, which Edgy silently drops on every regular write path."""

from datetime import datetime

import pytest

from fastedgy.app import FastEdgy
from fastedgy.test.models.product import Product

TARGET = datetime(2000, 1, 1, 12, 0, 0)


async def test_regular_writes_still_drop_read_only_fields(setup_db: FastEdgy) -> None:
    product = await Product.query.create(name="Probe", price="1.00", created_at=TARGET)

    fetched = await Product.query.get(id=product.id)
    assert fetched.created_at != TARGET

    fetched.created_at = TARGET
    await fetched.save()

    assert (await Product.query.get(id=product.id)).created_at != TARGET


async def test_apply_readonly_values_persists_on_insert(setup_db: FastEdgy) -> None:
    product = Product(name="Probe", price="1.00")
    product.apply_readonly_values({"created_at": TARGET})
    await product.save()

    fetched = await Product.query.get(id=product.id)
    assert fetched.created_at.replace(tzinfo=None) == TARGET


async def test_apply_readonly_values_persists_on_update(setup_db: FastEdgy) -> None:
    product = await Product.query.create(name="Probe", price="1.00")

    fetched = await Product.query.get(id=product.id)
    fetched.apply_readonly_values({"created_at": TARGET})
    await fetched.save()

    reloaded = await Product.query.get(id=product.id)
    assert reloaded.created_at.replace(tzinfo=None) == TARGET
    assert reloaded.name == "Probe"


async def test_overrides_are_consumed_by_the_save(setup_db: FastEdgy) -> None:
    product = await Product.query.create(name="Probe", price="1.00")

    fetched = await Product.query.get(id=product.id)
    fetched.apply_readonly_values({"created_at": TARGET})
    await fetched.save()

    assert fetched._readonly_overrides == {}


async def test_unknown_field_is_rejected(setup_db: FastEdgy) -> None:
    product = Product(name="Probe", price="1.00")

    with pytest.raises(ValueError, match="Unknown field 'nope'"):
        product.apply_readonly_values({"nope": 1})
