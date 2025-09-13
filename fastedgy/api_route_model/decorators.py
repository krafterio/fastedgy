# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Type, Callable, TypeVar

from fastedgy.api_route_model.registry import ADMIN_ROUTE_MODEL_REGISTRY_TOKEN, RouteModelRegistry, RouteModelOptions
from fastedgy.dependencies import get_service
from fastedgy.orm import Model


M = TypeVar('M', bound=Type[Model])


def api_route_model(
    **kwargs: RouteModelOptions,
) -> Callable[[M], M]:
    """
    Decorator to mark a model for auto-generating API routes.

    Args:
        **kwargs: Map of standard endpoint types to be enabled or disabled

    Returns:
        The decorated model class
    """
    def decorator(model_cls: M) -> M:
        rmr = get_service(RouteModelRegistry)
        rmr.register_model(model_cls, kwargs)

        return model_cls

    return decorator


def admin_api_route_model(
    **kwargs: RouteModelOptions,
) -> Callable[[M], M]:
    """
    Decorator to mark a model for auto-generating API routes for admin-users.

    Args:
        **kwargs: Map of standard endpoint types to be enabled or disabled

    Returns:
        The decorated model class
    """
    def decorator(model_cls: M) -> M:
        armr = get_service(ADMIN_ROUTE_MODEL_REGISTRY_TOKEN)
        armr.register_model(model_cls, kwargs)

        return model_cls

    return decorator


__all__ = [
    "api_route_model",
    "admin_api_route_model",
]
