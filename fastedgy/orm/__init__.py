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
from fastedgy.orm import access_guard, field_selector, filter, order_by
from fastedgy.orm.meta import Meta
from fastedgy.orm.relations.many import Many
from fastedgy.orm.transaction import (
    defer_after_commit,
    drain_signal_side_effects,
    retry_on_serialization,
    run_signal_side_effect,
    transaction,
    with_transaction,
)

from sqlalchemy.exc import SQLAlchemyError

from fastedgy.bus.service import Bus

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
    "Many",
    "StrictModel",
    "ReflectModel",
    "BaseModelType",
    "migration",
    "access_guard",
    "field_selector",
    "filter",
    "order_by",
    "defer_after_commit",
    "drain_signal_side_effects",
    "retry_on_serialization",
    "run_signal_side_effect",
    "transaction",
    "with_transaction",
]

# A handler that dies on a SQL error dooms the caller's transaction: the bus
# must surface it (instead of its per-handler isolation) so the @transaction
# serialization replay can do its job. Registered here so any process using
# the ORM gets the wiring, without coupling the bus package to SQLAlchemy.
Bus.register_critical_exception(SQLAlchemyError)
