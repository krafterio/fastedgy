# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Models that announce their writes, for the realtime tests.

Their own models rather than the shared ones: a decorated model announces every
write, and the rest of the suite should not pay a NOTIFY for writing a product.
"""

from fastedgy import context
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import WorkspaceableMixin, WorkspaceShareableMemberMixin, WorkspaceShareableMixin
from fastedgy.orm import fields
from fastedgy.orm.filter import R, global_filter
from fastedgy.orm.workspace_shareable import workspace_shareable_via
from fastedgy.realtime import realtime_model


@realtime_model()
class RtRecord(BaseModel, WorkspaceableMixin):
    """The plain case: a record owned by a scope, all three actions announced."""

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


@realtime_model(user_field="members.user")
class RtThread(BaseModel):
    name = fields.CharField(max_length=200, null=True)

    class Meta(BaseModel.Meta):
        tablename = "test_rt_threads"


class RtMember(BaseModel):
    thread = fields.ForeignKey(RtThread, on_delete="CASCADE", related_name="members")
    user = fields.ForeignKey("User", on_delete="CASCADE", related_name=False)

    class Meta(BaseModel.Meta):
        tablename = "test_rt_members"


@realtime_model(user_field="thread.members.user", fields=["thread"], relations=["thread"])
class RtPost(BaseModel):
    body = fields.CharField(max_length=200, null=True)
    thread = fields.ForeignKey(RtThread, on_delete="CASCADE", related_name="posts")

    class Meta(BaseModel.Meta):
        tablename = "test_rt_posts"


@realtime_model(user_field="post.thread.members.user", fields=["post"])
class RtReaction(BaseModel):
    emoji = fields.CharField(max_length=20, null=True)
    post = fields.ForeignKey(RtPost, on_delete="CASCADE", related_name="reactions")

    class Meta(BaseModel.Meta):
        tablename = "test_rt_reactions"


@global_filter(lambda: R("owner", "=", context.get_user_id()), apply=lambda model: context.get_user() is not None)
@realtime_model()
class RtSecret(BaseModel, WorkspaceableMixin):
    """Read by its owner alone: what it announces reaches no other member of its scope."""

    label = fields.CharField(max_length=200, null=True)
    owner = fields.ForeignKey("User", null=True, related_name=False)

    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        tablename = "test_rt_secrets"


class RtProject(BaseModel, WorkspaceableMixin, WorkspaceShareableMixin):
    """A root shared with members of other scopes, who read its tasks from there."""

    name = fields.CharField(max_length=200, null=True)

    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        tablename = "test_rt_projects"


class RtProjectMember(BaseModel, WorkspaceShareableMemberMixin):
    project = fields.ForeignKey(RtProject, on_delete="CASCADE", related_name="members")
    user = fields.ForeignKey("User", on_delete="CASCADE", related_name=False)

    class Meta(BaseModel.Meta):
        tablename = "test_rt_project_members"


@workspace_shareable_via("project")
@realtime_model(fields=["project"])
class RtTask(BaseModel, WorkspaceableMixin):
    """Hangs off a shared project: its members outside the scope hear about it too."""

    label = fields.CharField(max_length=200, null=True)
    project = fields.ForeignKey(RtProject, null=True, on_delete="CASCADE", related_name="tasks")

    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        tablename = "test_rt_tasks"


__all__ = [
    "RtChild",
    "RtMember",
    "RtNote",
    "RtOwned",
    "RtPost",
    "RtProject",
    "RtProjectMember",
    "RtReaction",
    "RtRecord",
    "RtSecret",
    "RtTask",
    "RtThread",
]
