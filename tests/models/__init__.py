# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from tests.models.user import User
from tests.models.workspace import Workspace
from tests.models.workspace_user import WorkspaceUser
from tests.models.workspace_extra_field import WorkspaceExtraField
from tests.models.attachment import Attachment
from tests.models.queued_task import QueuedTask
from tests.models.queued_task_log import QueuedTaskLog
from tests.models.queued_task_worker import QueuedTaskWorker
from tests.models.tag import Tag
from tests.models.category import Category
from tests.models.product import Product


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
    "STANDARD_MODELS",
    "DEMO_MODELS",
    "ALL_MODELS",
]
