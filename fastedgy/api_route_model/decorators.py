# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Type, Callable, TypeVar, Union, Sequence, cast
from enum import Enum

from fastapi.params import Depends
from fastedgy.api_route_model.registry import (
    ADMIN_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelRegistry,
    RouteModelOptions,
    RouteModelOptionsValue,
)
from fastedgy.dependencies import get_service, Token
from fastedgy.orm import Model


M = TypeVar("M", bound=Type[Model])


def build_api_route_model_decorator(
    default_registry: Type[RouteModelRegistry] | Token[RouteModelRegistry],
) -> Callable[..., Callable[[M], M]]:
    """
    Factory function to build an API route model decorator.

    Args:
        default_registry: Default registry if no registry is specified

    Returns:
        A decorator function
    """

    def decorator_factory(
        prefix: str | None = None,
        tags: list[Union[str, Enum]] | None = None,
        dependencies: Sequence[Depends] | None = None,
        actions: dict[str, RouteModelOptionsValue] | None = None,
        registry: Type[RouteModelRegistry] | Token[RouteModelRegistry] | None = None,
        **kwargs: RouteModelOptionsValue,
    ) -> Callable[[M], M]:
        """
        Decorator to mark a model for auto-generating API routes.

        Args:
            prefix: Custom route prefix (default: /{tablename})
            tags: Custom tags for OpenAPI documentation
            dependencies: Route-level dependencies
            actions: Dictionary of actions (useful for reserved Python keywords like "import")
            registry: Specific registry to use (overrides default registry)
            **kwargs: Map of standard endpoint types to be enabled or disabled

        Returns:
            The decorated model class
        """

        def decorator(model_cls: M) -> M:
            target_registry = registry if registry is not None else default_registry
            registry_instance = get_service(target_registry)

            # Merge explicit actions dict with kwargs
            all_actions = {**(actions or {}), **kwargs}
            options = cast(
                RouteModelOptions,
                {
                    "prefix": prefix,
                    "tags": tags,
                    "dependencies": dependencies,
                    "actions": all_actions,
                },
            )
            registry_instance.register_model(model_cls, options)

            return model_cls

        return decorator

    return decorator_factory


# Create the decorators using the factory
api_route_model = build_api_route_model_decorator(RouteModelRegistry)
api_route_model.__doc__ = """
Decorator to mark a model for auto-generating API routes.

Args:
    prefix: Custom route prefix (default: /{tablename})
    tags: Custom tags for OpenAPI documentation
    dependencies: Route-level dependencies
    actions: Dictionary of actions (useful for reserved Python keywords like "import")
    registry: Specific registry to use (e.g., ADMIN_ROUTE_MODEL_REGISTRY_TOKEN)
    **kwargs: Map of standard endpoint types to be enabled or disabled

Returns:
    The decorated model class
"""

admin_api_route_model = build_api_route_model_decorator(
    ADMIN_ROUTE_MODEL_REGISTRY_TOKEN
)
admin_api_route_model.__doc__ = """
Decorator to mark a model for auto-generating API routes for admin-users.

Args:
    prefix: Custom route prefix (default: /{tablename})
    tags: Custom tags for OpenAPI documentation
    dependencies: Route-level dependencies
    actions: Dictionary of actions (useful for reserved Python keywords like "import")
    **kwargs: Map of standard endpoint types to be enabled or disabled

Returns:
    The decorated model class
"""


__all__ = [
    "build_api_route_model_decorator",
    "api_route_model",
    "admin_api_route_model",
]
