# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import importlib

from typing import TYPE_CHECKING, Any

from edgy import (
    Database,
    Registry,
    Model,
    StrictModel,
    ReflectModel,
)
from edgy.core.db.models.types import BaseModelType
from fastedgy.orm import field_selector, filter, order_by
from fastedgy.orm.meta import Meta
from fastedgy.orm.transaction import (
    retry_on_serialization,
    transaction,
    with_transaction,
)

# ``migration`` pulls Alembic, which is only needed by the ``db`` CLI commands.
# Loading it lazily keeps it out of the app/serve/runtime import path.
if TYPE_CHECKING:
    from fastedgy.orm import migration as migration


def __getattr__(name: str) -> Any:
    if name == "migration":
        module = importlib.import_module(f"{__name__}.migration")
        globals()["migration"] = module
        return module

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Database",
    "Registry",
    "Model",
    "Meta",
    "StrictModel",
    "ReflectModel",
    "BaseModelType",
    "migration",
    "field_selector",
    "filter",
    "order_by",
    "retry_on_serialization",
    "transaction",
    "with_transaction",
]
