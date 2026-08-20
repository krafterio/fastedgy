# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from collections.abc import Sequence
from enum import Enum
from typing import cast

from fastapi import APIRouter
from fastapi.params import Depends

from fastedgy.api_route_model.action import ApiRouteActionRegistry
from fastedgy.api_route_model.registry import (
    CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelActionOptions,
    RouteModelOptions,
    RouteModelRegistry,
)
from fastedgy.dependencies import Token, get_service
from fastedgy.models.base import BaseModel, BaseView

logger = logging.getLogger("api_route_model.generator")


def generate_router_for_model(
    registry: RouteModelRegistry, model_cls: type[BaseModel | BaseView], tags: bool = True
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
        logger.warning(f"Model {model_cls.__name__} is not registered, skipping router generation")
        return None

    options = registry.get_model_options(model_cls)

    # Extract router-level options from RouteModelOptions
    router_tags: list[str | Enum] | None = options.get("tags")
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
            action_cls.register_route(router, model_cls, cast(RouteModelActionOptions, action_opts))

    return router


def get_all_generated_routers(
    registry: type[RouteModelRegistry] | Token[RouteModelRegistry] = RouteModelRegistry,
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


def get_all_generated_console_routers() -> dict[str, APIRouter]:
    """
    Get all auto-generated routers for registered console models.

    Returns:
        A dictionary mapping route prefixes to routers
    """
    return get_all_generated_routers(CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN, tags=False)


# Deprecated alias — use `get_all_generated_console_routers`. Kept for backward compatibility.
get_all_generated_admin_routers = get_all_generated_console_routers


__all__ = [
    "get_all_generated_admin_routers",
    "get_all_generated_console_routers",
    "get_all_generated_routers",
]
