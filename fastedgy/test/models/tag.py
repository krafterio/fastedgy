# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel
from fastedgy.api_route_model import api_route_model


@api_route_model()
class Tag(BaseModel):
    name = fields.CharField(max_length=100)

    class Meta(BaseModel.Meta):
        tablename = "test_tags"


__all__ = [
    "Tag",
]
