# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

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


__all__ = [
    "is_global_storage_model",
    "is_global_storage_path",
]
