# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import warnings

import edgy
from sqlalchemy.exc import SAWarning

from fastedgy.orm import fields


def test_a_foreign_key_marked_use_alter_lets_a_cycle_of_tables_sort() -> None:
    models = edgy.Registry(database="postgresql+asyncpg://localhost/cycle")

    class Home(edgy.Model):
        address = fields.ForeignKey("Place", null=True, use_alter=True)

        class Meta:
            registry = models
            tablename = "homes"

    class Place(edgy.Model):
        home = fields.ForeignKey("Home", null=True)

        class Meta:
            registry = models
            tablename = "places"

    metadata = Home.table.metadata
    assert Place.table.metadata is metadata

    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        tables = [table.name for table in metadata.sorted_tables]

    assert tables == ["homes", "places"]
    assert [constraint.use_alter for constraint in Home.table.foreign_key_constraints] == [True]
    assert [constraint.use_alter for constraint in Place.table.foreign_key_constraints] == [False]
