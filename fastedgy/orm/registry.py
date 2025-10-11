# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy import (
    Registry,
    Model,
)


_lazy_models: set[type] = set()


def lazy_register_model(model_class: type) -> None:
    if (
        hasattr(model_class, "meta")
        and hasattr(model_class.meta, "abstract")
        and not model_class.meta.abstract
    ):
        _lazy_models.add(model_class)


def register_lazy_models(registry: Registry) -> None:
    """
    Register all models registered with the `lazy_register_model` function.

    Args:
        registry: The instance of the Registry
    """
    global _lazy_models

    from edgy.core.db.context_vars import FALLBACK_TARGET_REGISTRY

    if FALLBACK_TARGET_REGISTRY.get() is None:
        FALLBACK_TARGET_REGISTRY.set(registry)

    for model_class in _lazy_models:
        if not model_class.meta.abstract:
            model_class.add_to_registry(registry)

    _lazy_models = set()


__all__ = [
    "lazy_register_model",
    "register_lazy_models",
]
