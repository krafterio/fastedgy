# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel
from fastedgy.api_route_model import api_route_model

from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product


def note_targets() -> list[type]:
    return [Product, Category]


@api_route_model()
class Note(BaseModel):
    content = fields.CharField(max_length=255)
    subject = fields.GenericForeignKey(to=note_targets, related_name="notes", null=True)
    pinned_on = fields.GenericForeignKey(
        to=["Product"],
        model_column="pinned_model",
        id_column="pinned_ref",
        null=True,
    )

    class Meta(BaseModel.Meta):
        tablename = "test_notes"


__all__ = [
    "Note",
    "note_targets",
]
