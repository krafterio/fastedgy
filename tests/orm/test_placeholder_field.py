# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A placeholder field holds no column: it stands for a field of another type, whose pydantic type, default and
metadata type it takes, and gives the database nothing to write."""

from fastedgy.metadata_model.generator import generate_metadata_field_type
from fastedgy.orm import fields


def test_it_takes_the_type_and_the_default_of_the_field_it_stands_for() -> None:
    field = fields.PlaceholderField(fields.JSONField, null=True, exclude=False)

    assert generate_metadata_field_type(field) == "json"
    assert field.default is None
    assert not field.exclude


def test_a_default_of_its_own_wins_over_the_one_of_its_type() -> None:
    field = fields.PlaceholderField(fields.IntegerField, default=3)

    assert generate_metadata_field_type(field) == "integer"
    assert field.default == 3


def test_it_gives_the_database_nothing_to_write() -> None:
    field = fields.PlaceholderField(fields.JSONField, null=True, exclude=False, default={})

    assert field.clean("data", {"items": [1]}) == {}
    assert field.get_default_values("data", {}) == {}
    assert field.get_columns("data") == []
