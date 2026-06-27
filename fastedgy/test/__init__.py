# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING

from fastedgy.test.app import (
    APP_TITLE,
    APP_VERSION,
    APP_DESCRIPTION,
    API_PREFIX,
    build_app,
    dump_openapi,
)

# The synthetic test models register themselves with the ORM on import, so they
# are exposed lazily (PEP 562): importing fastedgy.test — for the fixtures or the
# database helpers — must not pollute the registry, otherwise a downstream project
# building its own app hits a model-name collision.
_LAZY_MODELS = frozenset(
    {
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
    }
)

if TYPE_CHECKING:
    from fastedgy.test.models import (
        User,
        Workspace,
        WorkspaceUser,
        WorkspaceExtraField,
        Attachment,
        QueuedTask,
        QueuedTaskLog,
        QueuedTaskWorker,
        Tag,
        Category,
        Product,
        STANDARD_MODELS,
        DEMO_MODELS,
        ALL_MODELS,
    )


def __getattr__(name: str):
    if name in _LAZY_MODELS:
        from fastedgy.test import models

        return getattr(models, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "APP_TITLE",
    "APP_VERSION",
    "APP_DESCRIPTION",
    "API_PREFIX",
    "build_app",
    "dump_openapi",
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
