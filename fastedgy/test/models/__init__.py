# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.test.models.user import User
from fastedgy.test.models.workspace import Workspace
from fastedgy.test.models.workspace_user import WorkspaceUser
from fastedgy.test.models.workspace_extra_field import WorkspaceExtraField
from fastedgy.test.models.attachment import Attachment
from fastedgy.test.models.queued_task import QueuedTask
from fastedgy.test.models.queued_task_log import QueuedTaskLog
from fastedgy.test.models.queued_task_worker import QueuedTaskWorker
from fastedgy.test.models.tag import Tag
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product
from fastedgy.test.models.global_filter import (
    GfArticle,
    GfOwnedMixin,
    GfPrivateDoc,
    GfSharedDoc,
    GfLink,
)
from fastedgy.test.models.fs_optimize import (
    FsoBrand,
    FsoCategory,
    FsoTag,
    FsoProduct,
)


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
]

ALL_MODELS = STANDARD_MODELS + DEMO_MODELS


__all__ = [
    "User",
    "Workspace",
    "WorkspaceUser",
    "WorkspaceExtraField",
    "Attachment",
    "QueuedTask",
    "QueuedTaskLog",
    "QueuedTaskWorker",
    "Tag",
    "Category",
    "Product",
    "GfArticle",
    "GfOwnedMixin",
    "GfPrivateDoc",
    "GfSharedDoc",
    "GfLink",
    "FsoBrand",
    "FsoCategory",
    "FsoTag",
    "FsoProduct",
    "STANDARD_MODELS",
    "DEMO_MODELS",
    "ALL_MODELS",
]
