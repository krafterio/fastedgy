# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.test.models.category import Category
from fastedgy.test.models.note import Note
from fastedgy.test.models.product import Product
from fastedgy.test.models.tag import Tag


async def _create_product(name: str = "Widget") -> Product:
    return await Product.query.create(name=name, price="9.99")


async def test_embedded_columns_use_default_and_custom_names(setup_db: FastEdgy) -> None:
    columns = Note.table.columns

    assert "subject_model" in columns
    assert "subject_id" in columns
    assert "pinned_model" in columns
    assert "pinned_ref" in columns
    assert "subject" not in columns
    assert "pinned_on" not in columns


async def test_assign_instance_fills_columns_and_loads_back(setup_db: FastEdgy) -> None:
    product = await _create_product()
    note = Note(content="about a product", subject=product)
    await note.save()

    fresh = await Note.query.get(id=note.id)
    assert fresh.subject_model == "product"
    assert fresh.subject_id == product.id

    loaded = await fresh.subject
    assert isinstance(loaded, Product)
    assert loaded.id == product.id


async def test_targets_can_switch_model_per_row(setup_db: FastEdgy) -> None:
    category = await Category.query.create(name="Bikes")
    note = Note(content="about a category")
    note.subject = category
    await note.save()

    fresh = await Note.query.get(id=note.id)
    loaded = await fresh.subject
    assert isinstance(loaded, Category)
    assert loaded.id == category.id


async def test_assign_none_clears_columns(setup_db: FastEdgy) -> None:
    product = await _create_product()
    note = Note(content="cleared", subject=product)
    await note.save()

    note.subject = None
    await note.save()

    fresh = await Note.query.get(id=note.id)
    assert fresh.subject_model is None
    assert fresh.subject_id is None
    assert await fresh.subject is None


async def test_assign_mapping_value(setup_db: FastEdgy) -> None:
    product = await _create_product()
    note = Note(content="mapped", subject={"model": "product", "id": product.id})
    await note.save()

    fresh = await Note.query.get(id=note.id)
    loaded = await fresh.subject
    assert isinstance(loaded, Product)
    assert loaded.id == product.id


async def test_flat_columns_stay_writable(setup_db: FastEdgy) -> None:
    product = await _create_product()
    note = Note(content="flat", subject_model="product", subject_id=product.id)
    await note.save()

    fresh = await Note.query.get(id=note.id)
    loaded = await fresh.subject
    assert isinstance(loaded, Product)
    assert loaded.id == product.id


async def test_filter_by_target_instance(setup_db: FastEdgy) -> None:
    product = await _create_product()
    other = await _create_product("Other")
    await Note.query.create(content="match", subject=product)
    await Note.query.create(content="no match", subject=other)

    notes = await Note.query.filter(subject=product).all()

    assert [note.content for note in notes] == ["match"]


async def test_rejects_target_outside_allowed_models(setup_db: FastEdgy) -> None:
    tag = await Tag.query.create(name="not allowed")

    with pytest.raises(ValueError):
        Note(content="invalid", subject=tag)


async def test_rejects_unsaved_target_instance(setup_db: FastEdgy) -> None:
    product = Product(name="Unsaved", price="1.00")

    with pytest.raises(ValueError):
        Note(content="invalid", subject=product)


async def test_rejects_unknown_mapping_model(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError):
        Note(content="invalid", subject={"model": "tag", "id": 1})


async def test_string_targets_with_custom_columns(setup_db: FastEdgy) -> None:
    product = await _create_product()
    note = Note(content="pinned", pinned_on=product)
    await note.save()

    fresh = await Note.query.get(id=note.id)
    assert fresh.pinned_model == "product"
    assert fresh.pinned_ref == product.id

    loaded = await fresh.pinned_on
    assert isinstance(loaded, Product)
    assert loaded.id == product.id


async def test_loaded_target_is_cached_per_instance(setup_db: FastEdgy) -> None:
    product = await _create_product()
    note = Note(content="cached", subject=product)
    await note.save()

    fresh = await Note.query.get(id=note.id)
    first = await fresh.subject
    await product.delete()
    second = await fresh.subject

    assert first is second
