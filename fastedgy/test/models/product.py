# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import SearchableMixin
from fastedgy.api_route_model import api_route_model

from fastedgy.test.models.category import Category
from fastedgy.test.models.tag import Tag


@api_route_model()
class Product(BaseModel, SearchableMixin):
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    is_active = fields.BooleanField(default=True)
    quantity = fields.IntegerField(default=0)
    rating = fields.FloatField(null=True)
    released_on = fields.DateField(null=True)
    published_at = fields.DateTimeField(null=True)
    reference = fields.UUIDField(null=True)
    details = fields.JSONField(null=True)
    secret_code = fields.CharField(max_length=64, null=True, exclude=True)
    category = fields.ForeignKey(Category, null=True, related_name="products")
    tags = fields.ManyToMany(Tag, related_name="products")

    class Meta(BaseModel.Meta, SearchableMixin.Meta):
        tablename = "test_products"


__all__ = [
    "Product",
]
