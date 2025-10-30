# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from enum import Enum
import logging

from typing import Sequence, Type, Union, cast

from fastapi import APIRouter

from fastapi.params import Depends
from fastedgy.dependencies import get_service, Token
from fastedgy.orm import Model
from fastedgy.api_route_model.registry import (
    ADMIN_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelActionOptions,
    RouteModelOptions,
    RouteModelOptionsValue,
    RouteModelRegistry,
)
from fastedgy.api_route_model.action import ApiRouteActionRegistry


logger = logging.getLogger("api_route_model.generator")


def generate_router_for_model(
    registry: RouteModelRegistry, model_cls: Type[Model], tags: bool = True
) -> APIRouter | None:
    """
    Generate a FastAPI router for a model.

    Args:
        registry: The registry to use
        model_cls: The Edgy model class
        tags: Whether or not to include tags in the generated routes

    Returns:
        A FastAPI router with CRUD endpoints
    """
    if not registry.is_model_registered(model_cls):
        logger.warning(
            f"Model {model_cls.__name__} is not registered, skipping router generation"
        )
        return None

    options = registry.get_model_options(model_cls)

    # Extract router-level options from RouteModelOptions
    router_tags: list[Union[str, Enum]] | None = options.get("tags")
    router_dependencies: Sequence[Depends] | None = options.get("dependencies")
    actions_options: RouteModelOptions = options.get("actions", {})

    # Fallback to default tags if not provided and tags flag is True
    if tags and router_tags is None:
        router_tags = [str(model_cls.meta.tablename)]
    elif not tags:
        router_tags = None

    # Create router with extracted options
    router = APIRouter(tags=router_tags, dependencies=router_dependencies)

    # Get all registered actions
    arar = get_service(ApiRouteActionRegistry)
    all_actions = arar.get_all_actions()

    # Register each action that is enabled
    for action_name, action_cls in all_actions.items():
        if action_cls.should_register(actions_options):
            action_opts = actions_options.get(action_name, {})
            action_opts = action_opts if isinstance(action_opts, dict) else {}
            action_cls.register_route(
                router, model_cls, cast(RouteModelActionOptions, action_opts)
            )

    return router


def get_all_generated_routers(
    registry: Type[RouteModelRegistry] | Token[RouteModelRegistry] = RouteModelRegistry,
    tags: bool = True,
) -> dict[str, APIRouter]:
    """
    Get all auto-generated routers for registered models.

    Args:
        registry: Either RouteModelRegistry class or a Token for a registry
        tags: Whether or not to include tags in the generated routes

    Returns:
        A dictionary mapping route prefixes to routers
    """
    routers = {}
    registry_instance = get_service(registry)

    registered_models = list(registry_instance.get_registered_models())

    for model_cls in registered_models:
        router = generate_router_for_model(registry_instance, model_cls, tags=tags)

        if router:
            options = registry_instance.get_model_options(model_cls)
            opt_prefix: str | None = options.get("prefix")

            if opt_prefix:
                prefix = f"{opt_prefix}/{model_cls.meta.tablename}"
            else:
                prefix = f"/{model_cls.meta.tablename}"

            routers[prefix] = router

    return routers


def get_all_generated_admin_routers() -> dict[str, APIRouter]:
    """
    Get all auto-generated routers for registered admin models.

    Returns:
        A dictionary mapping route prefixes to routers
    """
    return get_all_generated_routers(ADMIN_ROUTE_MODEL_REGISTRY_TOKEN, tags=False)


__all__ = [
    "get_all_generated_routers",
    "get_all_generated_admin_routers",
]
