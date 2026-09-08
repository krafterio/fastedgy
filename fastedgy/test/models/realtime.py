# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Models that announce their writes, for the realtime tests.

Their own models rather than the shared ones: a decorated model announces every
write, and the rest of the suite should not pay a NOTIFY for writing a product.
"""

from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.orm import fields
from fastedgy.realtime import realtime_model


@realtime_model()
class RtRecord(BaseModel, WorkspaceableMixin):
    """The plain case: a workspace-owned record, all three actions announced."""

    name = fields.CharField(max_length=200)

    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        tablename = "test_rt_records"


@realtime_model(fields={"record_id": "record"}, relations=["record"])
class RtChild(BaseModel, WorkspaceableMixin):
    """Hangs off a record: carries its parent's id, and reaches its channel."""

    label = fields.CharField(max_length=200, null=True)
    record = fields.ForeignKey(RtRecord, null=True, related_name="children")

    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        tablename = "test_rt_children"


@realtime_model(fields=["target_model", "target_ref"], relations=["target"])
class RtNote(BaseModel, WorkspaceableMixin):
    """Points at whatever it is attached to: the generic foreign key case."""

    content = fields.CharField(max_length=200, null=True)
    target = fields.GenericForeignKey(
        to=["RtRecord", "RtChild"],
        model_column="target_model",
        id_column="target_ref",
        related_name="rt_notes",
        null=True,
    )

    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        tablename = "test_rt_notes"


@realtime_model(user_field="user", delete=False)
class RtOwned(BaseModel, WorkspaceableMixin):
    """Belongs to a person rather than to a space, and never announces a delete."""

    label = fields.CharField(max_length=200, null=True)
    user = fields.ForeignKey("User", null=True, related_name="rt_owned")

    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        tablename = "test_rt_owned"


__all__ = [
    "RtChild",
    "RtNote",
    "RtOwned",
    "RtRecord",
]
