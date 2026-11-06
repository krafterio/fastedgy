# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields


@api_route_model()
class Folder(BaseModel):
    name = fields.CharField(max_length=100)
    parent = fields.ForeignKey("Folder", null=True, on_delete="CASCADE")
    category = fields.ForeignKey("Category", on_delete="CASCADE", related_name="folders")

    class Meta(BaseModel.Meta):
        tablename = "test_folders"


__all__ = [
    "Folder",
]
