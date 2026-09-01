# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.orm.order_by import OrderByList
from fastedgy.schemas import computed_field, computed_field_deps


class FsoBrand(BaseModel):
    name = fields.CharField(max_length=200)
    motto = fields.CharField(max_length=200, null=True)
    rank = fields.IntegerField(default=0)

    # An ORM ComputedField, read through a relation: the flavour that has no
    # property for the mark to sit on.
    tagline: str | None = fields.ComputedField(getter="get_tagline", exclude=False, read_only=True)

    class Meta(BaseModel.Meta):
        tablename = "test_fso_brands"

    @classmethod
    @computed_field_deps("name", "motto")
    def get_tagline(cls, field, instance, owner=None) -> str:
        return f"{instance.name}: {instance.motto}"


class FsoCategory(BaseModel):
    name = fields.CharField(max_length=120)
    summary = fields.TextField(null=True)
    brand = fields.ForeignKey(FsoBrand, null=True, related_name="categories")

    class Meta(BaseModel.Meta):
        tablename = "test_fso_categories"


class FsoTag(BaseModel):
    name = fields.CharField(max_length=100)
    color = fields.CharField(max_length=20, null=True)

    class Meta(BaseModel.Meta):
        tablename = "test_fso_tags"
        default_order_by: OrderByList = [("name", "asc")]


class FsoProduct(BaseModel):
    name = fields.CharField(max_length=200)
    sku = fields.CharField(max_length=50, null=True)
    price = fields.FloatField(default=0.0)
    quantity = fields.IntegerField(default=0)
    internal_note = fields.CharField(max_length=200, null=True, exclude=True)
    category = fields.ForeignKey(FsoCategory, null=True, related_name="products")
    tags = fields.ManyToMany(FsoTag, related_name="fso_products")

    # The ORM flavour of the two Pydantic cases below: one marked with what its
    # getter reads, one left unmarked.
    stock_label: str | None = fields.ComputedField(getter="get_stock_label", exclude=False, read_only=True)

    undeclared_label: str | None = fields.ComputedField(getter="get_undeclared_label", exclude=False, read_only=True)

    class Meta(BaseModel.Meta):
        tablename = "test_fso_products"

    @classmethod
    @computed_field_deps("price", "quantity")
    def get_stock_label(cls, field, instance, owner=None) -> str:
        return f"{instance.price} x {instance.quantity}"

    @classmethod
    def get_undeclared_label(cls, field, instance, owner=None) -> str:
        return f"{instance.name} ({instance.sku})"

    @computed_field
    @computed_field_deps("price", "quantity")
    @property
    def stock_value(self) -> float:
        return float(self.price or 0.0) * float(self.quantity or 0)

    @computed_field
    @computed_field_deps("category.brand.name")
    @property
    def brand_name(self) -> str | None:
        category = getattr(self, "category", None)
        brand = getattr(category, "brand", None) if category is not None else None

        return getattr(brand, "name", None) if brand is not None else None

    @computed_field
    @property
    def display_label(self) -> str:
        return f"{self.name} x{self.quantity}"


__all__ = [
    "FsoBrand",
    "FsoCategory",
    "FsoProduct",
    "FsoTag",
]
