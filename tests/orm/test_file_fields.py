# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, cast

from fastedgy.metadata_model.generator import generate_metadata_field
from fastedgy.orm import fields
from fastedgy.orm.fields import CharField, FileField, ImageField, StoredImage, stored_image_of
from fastedgy.orm.filter import get_filter_operators
from fastedgy.test.models.product import Product


def test_a_file_field_keeps_the_column_of_a_char_field() -> None:
    image = Product.meta.fields["image"]
    name = Product.meta.fields["name"]

    assert isinstance(image, CharField)
    assert image.field_type is str
    assert repr(image.get_columns("image")[0].type) == "String(length=500)"
    assert get_filter_operators(image) == get_filter_operators(name)


def test_an_image_field_is_told_apart_from_a_char_field() -> None:
    assert isinstance(Product.meta.fields["image"], ImageField)
    assert isinstance(Product.meta.fields["image"], FileField)
    assert not isinstance(Product.meta.fields["name"], FileField)
    assert not isinstance(fields.FileField(max_length=255, null=True), ImageField)


def test_the_metadata_still_expose_a_char() -> None:
    assert generate_metadata_field(Product, Product.meta.fields["image"]).type == "char"
    assert generate_metadata_field(Product, Product.meta.fields["name"]).type == "char"


def test_an_image_field_holds_its_optimization() -> None:
    assert stored_image_of(Product, "image") == StoredImage(max_side=2560, format="webp", quality=85)
    assert cast(Any, fields.ImageField(max_length=255, max_side=640, quality=70)).stored_image == StoredImage(
        max_side=640, quality=70
    )
    assert stored_image_of(Product, "name") is None
