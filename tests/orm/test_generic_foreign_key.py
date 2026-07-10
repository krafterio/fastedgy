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


async def test_denied_target_loads_as_none(setup_db: FastEdgy) -> None:
    from fastedgy.dependencies import get_service
    from fastedgy.orm.access_guard import AccessDeniedError, ModelAccessGuardRegistry, ModelAction
    from fastedgy.orm.field_selector import prefetch_generic_references

    product = await _create_product()
    note = Note(content="guarded", subject=product)
    await note.save()

    def deny_reads(model_cls: type, action: ModelAction, instance: object = None) -> None:
        if action == ModelAction.read:
            raise AccessDeniedError("denied")

    registry = get_service(ModelAccessGuardRegistry)
    registry.register(Product, deny_reads)

    try:
        fresh = await Note.query.get(id=note.id)
        assert await fresh.subject is None

        items = await Note.query.filter(id=note.id).all()
        await prefetch_generic_references(items, "subject.name")
        assert items[0].__dict__["_gfk_cache_subject"] is None
    finally:
        registry._guards.pop(Product, None)
        registry._resolved.clear()

    fresh = await Note.query.get(id=note.id)
    loaded = await fresh.subject
    assert loaded is not None and loaded.id == product.id


async def test_inverse_relation_lists_only_owned_rows(setup_db: FastEdgy) -> None:
    product = await _create_product()
    category = await Category.query.create(name="Bikes")
    await Note.query.create(content="on product", subject=product)
    await Note.query.create(content="on category", subject=category)

    product_notes = await product.notes.all()
    category_notes = await category.notes.all()

    assert [note.content for note in product_notes] == ["on product"]
    assert [note.content for note in category_notes] == ["on category"]


async def test_inverse_relation_ignores_same_id_on_other_model(setup_db: FastEdgy) -> None:
    product = await _create_product()
    category = await Category.query.create(name="Bikes")
    assert product.id == category.id

    await Note.query.create(content="only category", subject=category)

    assert await product.notes.all() == []
    assert len(await category.notes.all()) == 1


async def test_inverse_relation_add_and_remove(setup_db: FastEdgy) -> None:
    product = await _create_product()
    note = await Note.query.create(content="orphan")

    await product.notes.add(note)
    fresh = await Note.query.get(id=note.id)
    assert fresh.subject_model == "product"
    assert fresh.subject_id == product.id

    await product.notes.remove(fresh)
    cleared = await Note.query.get(id=note.id)
    assert cleared.subject_model is None
    assert cleared.subject_id is None


async def test_no_inverse_without_related_name(setup_db: FastEdgy) -> None:
    from typing import Any, cast

    cast(Any, Note.meta.fields["pinned_on"]).targets()

    assert "notes" in Product.meta.fields
    assert not any(getattr(field, "generic_field_name", None) == "pinned_on" for field in Product.meta.fields.values())


async def test_filter_through_generic_reverse_relation(setup_db: FastEdgy) -> None:
    from fastedgy.orm.filter import R, filter_query

    product = await _create_product()
    other = await _create_product("Other")
    category = await Category.query.create(name="Bikes")
    await Note.query.create(content="hit", subject=product)
    await Note.query.create(content="hit", subject=category)
    await Note.query.create(content="miss", subject=other)

    products = await filter_query(Product.query, R("notes.content", "=", "hit")).all()

    assert [item.id for item in products] == [product.id]


async def test_filter_through_generic_reverse_relation_in_or_condition(setup_db: FastEdgy) -> None:
    from fastedgy.orm.filter import Or, R, filter_query

    product = await _create_product()
    other = await _create_product("Other")
    await Note.query.create(content="hit", subject=product)

    products = await filter_query(
        Product.query,
        Or(R("notes.content", "=", "hit"), R("name", "=", "Other")),
    ).all()

    assert {item.id for item in products} == {product.id, other.id}


async def test_metadata_exposes_reference_and_inverse(setup_db: FastEdgy) -> None:
    from fastedgy.metadata_model.generator import generate_metadata_model

    note_metadata = await generate_metadata_model(Note)
    subject_field = note_metadata.fields["subject"]
    assert subject_field.type == "reference"
    assert subject_field.targets == ["category", "product"]

    product_metadata = await generate_metadata_model(Product)
    notes_field = product_metadata.fields["notes"]
    assert notes_field.type == "one2many"
    assert notes_field.target == "note"
