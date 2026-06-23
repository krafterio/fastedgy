# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel
from fastedgy.api_route_model import api_route_model


@api_route_model()
class Category(BaseModel):
    name = fields.CharField(max_length=120)
    description = fields.TextField(null=True)

    class Meta(BaseModel.Meta):
        tablename = "test_categories"


__all__ = [
    "Category",
]
