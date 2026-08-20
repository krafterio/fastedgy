# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.test.models.annotation import Annotation
from fastedgy.test.models.attachment import Attachment
from fastedgy.test.models.category import Category
from fastedgy.test.models.comment import Comment
from fastedgy.test.models.fs_optimize import (
    FsoBrand,
    FsoCategory,
    FsoProduct,
    FsoTag,
)
from fastedgy.test.models.global_filter import (
    GfArticle,
    GfLink,
    GfOwnedMixin,
    GfPrivateDoc,
    GfSharedDoc,
)
from fastedgy.test.models.note import Note
from fastedgy.test.models.product import Product
from fastedgy.test.models.queued_task import QueuedTask
from fastedgy.test.models.queued_task_log import QueuedTaskLog
from fastedgy.test.models.queued_task_worker import QueuedTaskWorker
from fastedgy.test.models.tag import Tag
from fastedgy.test.models.ticket import Ticket
from fastedgy.test.models.user import User
from fastedgy.test.models.workspace import Workspace
from fastedgy.test.models.workspace_extra_field import WorkspaceExtraField
from fastedgy.test.models.workspace_user import WorkspaceUser

STANDARD_MODELS = [
    User,
    Workspace,
    WorkspaceUser,
    WorkspaceExtraField,
    Attachment,
    QueuedTask,
    QueuedTaskLog,
    QueuedTaskWorker,
]

DEMO_MODELS = [
    Tag,
    Category,
    Product,
    Comment,
    Note,
    Annotation,
    Ticket,
]

ALL_MODELS = STANDARD_MODELS + DEMO_MODELS


__all__ = [
    "ALL_MODELS",
    "DEMO_MODELS",
    "STANDARD_MODELS",
    "Annotation",
    "Attachment",
    "Category",
    "Comment",
    "FsoBrand",
    "FsoCategory",
    "FsoProduct",
    "FsoTag",
    "GfArticle",
    "GfLink",
    "GfOwnedMixin",
    "GfPrivateDoc",
    "GfSharedDoc",
    "Note",
    "Product",
    "QueuedTask",
    "QueuedTaskLog",
    "QueuedTaskWorker",
    "Tag",
    "Ticket",
    "User",
    "Workspace",
    "WorkspaceExtraField",
    "WorkspaceUser",
]
