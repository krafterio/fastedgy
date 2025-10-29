# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging

from typing import Type

from fastapi import APIRouter

from fastedgy.dependencies import get_service, Token
from fastedgy.orm import Model
from fastedgy.api_route_model.registry import (
    ADMIN_ROUTE_MODEL_REGISTRY_TOKEN,
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
    router_prefix = options.get("prefix")
    router_tags = options.get("tags")
    router_dependencies = options.get("dependencies")
    actions_options = options.get("actions", {})

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
            action_cls.register_route(router, model_cls, action_opts)

    return router


def build_all_generated_routers(
    registry_or_token: Type[RouteModelRegistry] | Token[RouteModelRegistry],
    tags: bool = True,
) -> dict[str, APIRouter]:
    """
    Build all auto-generated routers for a given registry.

    Args:
        registry_or_token: Either RouteModelRegistry class or a Token for a registry
        tags: Whether or not to include tags in the generated routes

    Returns:
        A dictionary mapping route prefixes to routers
    """
    routers = {}
    registry = get_service(registry_or_token)

    registered_models = list(registry.get_registered_models())

    for model_cls in registered_models:
        router = generate_router_for_model(registry, model_cls, tags=tags)

        if router:
            # Build prefix: custom prefix + table name
            options = registry.get_model_options(model_cls)
            custom_prefix = options.get("prefix")
            if custom_prefix:
                prefix = f"{custom_prefix}/{model_cls.meta.tablename}"
            else:
                prefix = f"/{model_cls.meta.tablename}"
            routers[prefix] = router

    return routers


def get_all_generated_routers() -> dict[str, APIRouter]:
    """
    Get all auto-generated routers for registered models.

    Returns:
        A dictionary mapping route prefixes to routers
    """
    return build_all_generated_routers(RouteModelRegistry, tags=True)


def get_all_generated_admin_routers() -> dict[str, APIRouter]:
    """
    Get all auto-generated routers for registered admin models.

    Returns:
        A dictionary mapping route prefixes to routers
    """
    return build_all_generated_routers(ADMIN_ROUTE_MODEL_REGISTRY_TOKEN, tags=False)
