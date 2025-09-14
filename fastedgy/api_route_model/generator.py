# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging

from typing import Type

from fastapi import APIRouter

from fastedgy.dependencies import get_service
from fastedgy.orm import Model
from fastedgy.api_route_model.registry import (
    ADMIN_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelRegistry,
)
from fastedgy.api_route_model.actions import ApiRouteActionRegistry


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
    router = APIRouter(tags=[str(model_cls.meta.tablename)] if tags else None)

    # Get all registered actions
    arar = get_service(ApiRouteActionRegistry)
    all_actions = arar.get_all_actions()

    # Register each action that is enabled
    for action_name, action_cls in all_actions.items():
        if action_cls.should_register(options):
            action_opts = options.get(action_name, {})
            action_opts = action_opts if isinstance(action_opts, dict) else {}
            action_cls.register_route(router, model_cls, action_opts)

    return router


def get_all_generated_routers() -> dict[str, APIRouter]:
    """
    Get all auto-generated routers for registered models.

    Returns:
        A dictionary mapping route prefixes to routers
    """
    routers = {}
    rmr = get_service(RouteModelRegistry)

    registered_models = list(rmr.get_registered_models())

    for model_cls in registered_models:
        router = generate_router_for_model(rmr, model_cls)

        if router:
            prefix = f"/{model_cls.meta.tablename}"
            routers[prefix] = router

    return routers


def get_all_generated_admin_routers() -> dict[str, APIRouter]:
    """
    Get all auto-generated routers for registered admin models.

    Returns:
        A dictionary mapping route prefixes to routers
    """
    routers = {}
    armr = get_service(ADMIN_ROUTE_MODEL_REGISTRY_TOKEN)

    registered_models = list(armr.get_registered_models())

    for model_cls in registered_models:
        router = generate_router_for_model(armr, model_cls, tags=False)

        if router:
            prefix = f"/{model_cls.meta.tablename}"
            routers[prefix] = router

    return routers
