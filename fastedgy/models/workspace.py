# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n import _ts

import string
import random

from fastedgy.orm.order_by import OrderByList
from fastedgy.orm import fields
from fastedgy.models.base import BaseModel


def generate_slug(length=10) -> str:
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length))


class BaseWorkspace(BaseModel):
    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("Workspace")
        label_plural = _ts("Workspaces")
        default_order_by: OrderByList = [("name", "asc")]
        indexes = [
            fields.Index(fields=["name"]),
            fields.Index(fields=["slug"]),
        ]
        model_name: str | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        meta = getattr(cls, "Meta", None)
        if not meta or getattr(meta, "abstract", False):
            return

        if BaseWorkspace.Meta.model_name is None:
            BaseWorkspace.Meta.model_name = cls.__name__
            return

        if BaseWorkspace.Meta.model_name == cls.__name__:
            return

        raise RuntimeError(f"Multiple workspace models detected: {BaseWorkspace.Meta.model_name} and {cls.__name__}")

    name: str | None = fields.CharField(max_length=255, null=True, label=_ts("Name"))

    slug: str | None = fields.CharField(max_length=32, unique=True, label=_ts("Slug"))

    image_url: str | None = fields.CharField(max_length=255, null=True, label=_ts("Image"))


__all__ = [
    "generate_slug",
    "BaseWorkspace",
]
