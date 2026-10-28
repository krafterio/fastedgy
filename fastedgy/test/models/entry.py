# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.api_route_model import api_route_model
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.orm.filter import R
from fastedgy.orm.signals import pre_save
from fastedgy.test.models.category import Category

INBOX = "Inbox"


@api_route_model()
class Entry(BaseModel):
    """A row whose category stays required in the database while the API lets a
    creation leave it out: the signal below files it in the inbox."""

    label = fields.CharField(max_length=100)
    category = fields.ForeignKey(
        "Category",
        on_delete="CASCADE",
        related_name="entries",
        input_optional=True,
    )

    class Meta(BaseModel.Meta):
        tablename = "test_entries"


@pre_save.connect_via(Entry)
async def file_in_inbox(
    _: Any,
    instance: Entry,
    values: dict[str, Any],
    column_values: dict[str, Any],
    is_update: bool = False,
    **_kwargs: Any,
) -> None:
    if is_update or column_values.get("category") is not None:
        return

    inbox = await Category.query.filter(R("name", "=", INBOX)).first() or await Category(name=INBOX).save()
    instance.category = inbox
    values["category"] = inbox.id
    column_values["category"] = inbox.id


__all__ = [
    "INBOX",
    "Entry",
]
