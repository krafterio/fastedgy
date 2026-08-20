# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields


@api_route_model()
class Annotation(BaseModel):
    body = fields.CharField(max_length=255)
    anchor = fields.GenericForeignKey(
        to=["Product", "Category"],
        related_name="annotations",
        null=False,
    )

    class Meta(BaseModel.Meta):
        tablename = "test_annotations"


__all__ = [
    "Annotation",
]
