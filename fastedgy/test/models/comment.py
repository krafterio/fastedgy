# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel
from fastedgy.api_route_model import api_route_model

from fastedgy.test.models.product import Product


@api_route_model(create=False, patch=False, delete=False)
class Comment(BaseModel):
    """Read-only-through-the-API child model: exercises the relation guard."""

    content = fields.CharField(max_length=200)
    product = fields.ForeignKey(Product, null=True, related_name="comments")

    class Meta(BaseModel.Meta):
        tablename = "test_comments"
        # No public write action, yet forced synchronizable (mirrors models
        # synced through custom routes): the metadata override wins.
        synchronizable = True


__all__ = [
    "Comment",
]
