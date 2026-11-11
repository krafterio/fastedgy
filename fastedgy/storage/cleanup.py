# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The removal of the files records let go: replaced, cleared, or deleted with their record. A queued task runs it
once the transaction commits, and removes a file with its optimized variants only when no file field of any model
holds it any more."""

import logging
from functools import partial
from typing import Any

from fastedgy.dependencies import get_service
from fastedgy.metadata_model.generator import generate_metadata_name
from fastedgy.models.base import BaseView
from fastedgy.orm import Registry
from fastedgy.orm.fields import FileField
from fastedgy.orm.filter import R
from fastedgy.orm.signals import pre_delete
from fastedgy.orm.transaction import defer_after_commit, run_signal_side_effect
from fastedgy.storage.routing import is_global_storage_model
from fastedgy.storage.services import Storage

logger = logging.getLogger("fastedgy.storage")

type FieldColumn = tuple[Any, str]

_registered: set[type] = set()


def field_columns(field_type: type = FileField) -> list[FieldColumn]:
    """Every field of ``field_type`` of the registered models, as (model, field)."""
    return [
        (model_cls, name)
        for model_cls in get_service(Registry).models.values()
        if not issubclass(model_cls, BaseView)
        for name, model_field in model_cls.meta.fields.items()
        if isinstance(model_field, field_type)
    ]


def schedule_file_cleanup(model_cls: Any, field: str, path: str | None, global_storage: bool) -> None:
    """Queue, once the transaction commits, the removal of a file the ``field`` of a ``model_cls`` record let go.

    A field that is no file field holds a path only the storage routes write: its file goes only when it lies in the
    directory of the record's model, where the routes store them, or of its table, where 1.8.9 stored them, since
    other columns may hold the files of others."""
    if not path:
        return

    tablename = model_cls.meta.tablename
    own = (f"{generate_metadata_name(model_cls)}/", f"{tablename}/")

    if not isinstance(model_cls.meta.fields.get(field), FileField) and not path.startswith(own):
        return

    def queue() -> None:
        if "QueuedTask" not in get_service(Registry).models:
            run_signal_side_effect(
                partial(remove_unreferenced_file, path, global_storage, tablename, field), f"Remove {path}"
            )
            return

        from fastedgy.queued_task import QueuedTasks

        get_service(QueuedTasks).add_task(
            remove_unreferenced_file, path, global_storage, tablename, field, auto_remove=True
        )

    defer_after_commit(queue, key=("file-cleanup", path, global_storage))


async def remove_unreferenced_file(path: str, global_storage: bool, table: str, field: str) -> bool:
    """Queued task: remove a stored file and its optimized variants, unless a file field of any model, or the
    ``field`` of ``table`` it was let go from, still holds it. Returns whether it was removed."""
    columns = field_columns()
    origin = next((model for model in get_service(Registry).models.values() if model.meta.tablename == table), None)

    if origin is not None and (origin, field) not in columns:
        columns.append((origin, field))

    for model_cls, name in columns:
        if await model_cls.global_query.filter(R(name, "=", path), allow_excluded=True).exists():
            return False

    return await get_service(Storage).delete(path, global_storage=global_storage)


async def _let_go_with_their_records(sender: Any, instance: Any, model_instance: Any = None, **kwargs: Any) -> None:
    names = [name for name, model_field in sender.meta.fields.items() if isinstance(model_field, FileField)]

    if model_instance is not None:
        rows = [{name: model_instance.__dict__.get(name) for name in names}]
    else:
        rows = await instance.values(fields=names)

    global_storage = is_global_storage_model(sender)

    for row in rows:
        for name in names:
            schedule_file_cleanup(sender, name, row.get(name), global_storage)


def register_file_cleanup_signals() -> None:
    """Remove the files of the records deleted, for every registered model holding a file field."""
    for model_cls in {model_cls for model_cls, _ in field_columns()} - _registered:
        _registered.add(model_cls)
        pre_delete.connect(_let_go_with_their_records, sender=model_cls)


__all__ = [
    "field_columns",
    "register_file_cleanup_signals",
    "remove_unreferenced_file",
    "schedule_file_cleanup",
]
