# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Type, Callable, TypeVar
from edgy import Model

from fastedgy.dependencies import get_service
from fastedgy.metadata_model import MetadataModelRegistry


M = TypeVar('M', bound=Type[Model])


def metadata_model() -> Callable[[M], M]:
    """
    Decorator to mark a model for metadata exposure.

    Returns:
        The decorated model class
    """
    def decorator(model_cls: M) -> M:
        registry = get_service(MetadataModelRegistry)
        registry.register_model(model_cls) # type: ignore

        return model_cls

    return decorator


__all__ = [
    "metadata_model",
]
