# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, TypeVar

from fastedgy.models.base import BaseModel, BaseView
from fastedgy.dependencies import get_service
from fastedgy.metadata_model.registry import MetadataModelRegistry


M = TypeVar("M", bound=type[BaseModel | BaseView])


def metadata_model() -> Callable[[M], M]:
    """
    Decorator to mark a model for metadata exposure.

    Returns:
        The decorated model class
    """

    def decorator(model_cls: M) -> M:
        registry = get_service(MetadataModelRegistry)
        registry.register_model(model_cls)

        return model_cls

    return decorator


__all__ = [
    "metadata_model",
]
