# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.dependencies import get_service
from fastedgy.metadata_model.registry import MetadataModelRegistry
from fastedgy.models.base import BaseModel, BaseView


def is_global_storage_model(model_cls: type[BaseModel | BaseView]) -> bool:
    """Resolve the default storage routing of a model.

    A model is stored globally unless it carries a ``workspace`` field (e.g. via
    ``WorkspaceableMixin``). ``Meta.global_storage = True`` forces global storage
    for a workspace-scoped model.
    """
    if getattr(getattr(model_cls, "Meta", None), "global_storage", False):
        return True

    return "workspace" not in model_cls.meta.fields


async def is_global_storage_path(path: str) -> bool:
    """Resolve the default storage routing of a stored file path.

    The first path segment is the model directory used by the model field upload
    endpoint (tablename or metadata name). Unknown segments stay workspace-scoped.
    """
    segment = path.split("/", 1)[0]
    meta_registry = get_service(MetadataModelRegistry)

    if not await meta_registry.is_registered(segment):
        return False

    return is_global_storage_model(await meta_registry.get_model_from_metadata(segment))


async def resolve_workspace_for_path(path: str) -> Any | None:
    """Find the workspace owning a workspace-scoped stored file.

    Resolves the model from the first path segment, then the record whose file
    field holds this exact path, and returns its workspace. Lets back-office
    superusers download workspace-scoped files without the owning workspace in
    their request context.
    """
    from fastedgy.orm.fields import CharField
    from fastedgy.orm.filter import Or, R
    from fastedgy.orm.filter.builder import filter_query

    segment = path.split("/", 1)[0]
    meta_registry = get_service(MetadataModelRegistry)

    if not await meta_registry.is_registered(segment):
        return None

    model_cls = await meta_registry.get_model_from_metadata(segment)

    if "workspace" not in model_cls.meta.fields:
        return None

    candidates = [name for name, field in model_cls.meta.fields.items() if isinstance(field, CharField)]

    if not candidates:
        return None

    conditions = Or(*[R(name, "=", path) for name in candidates])
    record = await filter_query(model_cls.global_query, conditions, allow_excluded=True).first()

    if record is None:
        return None

    return getattr(record, "workspace", None)


__all__ = [
    "is_global_storage_model",
    "is_global_storage_path",
    "resolve_workspace_for_path",
]
