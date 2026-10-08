# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.metadata_model import metadata_model
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields


@metadata_model()
class Assignment(BaseModel):
    """A row whose foreign key the API hides, while a filter on the category
    still walks its reverse relation."""

    label = fields.CharField(max_length=100)
    category = fields.ForeignKey(
        "Category",
        on_delete="CASCADE",
        related_name="assignments",
        exclude=True,
    )

    class Meta(BaseModel.Meta):
        tablename = "test_assignments"


__all__ = [
    "Assignment",
]
