# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Union

from fastedgy import context
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.orm import fields
from fastedgy.orm.filter import R, global_filter

from fastedgy.test.models.user import User


@global_filter(lambda: R("is_active", "is true"))
@global_filter(lambda: R("stock", ">", 0))
class GfArticle(BaseModel, WorkspaceableMixin):
    title = fields.CharField(max_length=200)
    is_active = fields.BooleanField(default=True)
    stock = fields.IntegerField(default=0)

    class Meta(BaseModel.Meta):
        tablename = "test_gf_articles"


@global_filter(
    lambda: R("owner", "=", context.get_user_id()) if context.get_user_id() else None,
    apply=lambda cls: cls.__name__ != "GfSharedDoc",
)
class GfOwnedMixin(WorkspaceableMixin):
    class Meta:
        abstract = True

    owner: Union["User", None] = fields.ForeignKey(User, null=True, related_name="+")


class GfPrivateDoc(BaseModel, GfOwnedMixin):
    name = fields.CharField(max_length=200)

    class Meta(BaseModel.Meta):
        tablename = "test_gf_private_docs"


class GfSharedDoc(BaseModel, GfOwnedMixin):
    name = fields.CharField(max_length=200)

    class Meta(BaseModel.Meta):
        tablename = "test_gf_shared_docs"


class GfLink(BaseModel, WorkspaceableMixin):
    label = fields.CharField(max_length=200, null=True)
    doc = fields.ForeignKey(GfPrivateDoc, null=True, related_name="links")

    class Meta(BaseModel.Meta):
        tablename = "test_gf_links"


__all__ = [
    "GfArticle",
    "GfOwnedMixin",
    "GfPrivateDoc",
    "GfSharedDoc",
    "GfLink",
]
