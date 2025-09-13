# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy import (
    Registry,
    Model,
)


_lazy_models: set[type] = set()


def register_model(registry: Registry, model: type[Model]):
    """Register a model in the registry."""
    registry.models[model.__name__] = model
    model.database = registry.database
    model.meta.registry = registry


def lazy_register_model(model_class: type) -> None:
    if hasattr(model_class, 'meta') and hasattr(model_class.meta, 'abstract') and not model_class.meta.abstract:
        _lazy_models.add(model_class)


def register_lazy_models(registry: Registry) -> None:
    """
    Register all models registered with the `lazy_register_model` function.

    Args:
        registry: The instance of the Registry
    """
    global _lazy_models

    for model_class in _lazy_models:
        if not model_class.meta.abstract:
            register_model(registry, model_class)

    _lazy_models = set()


__all__ = [
    "register_model",
    "lazy_register_model",
    "register_lazy_models",
]
