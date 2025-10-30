# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from typing import Type, Callable

from fastapi import APIRouter
from fastedgy.api_route_model.generator import get_all_generated_routers
from fastedgy.api_route_model.registry import (
    ADMIN_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelRegistry,
)
from fastedgy.dependencies import get_service, Token
from fastedgy.metadata_model import MetadataModelRegistry


logger = logging.getLogger("api_route_model.router")


def register_api_route_models(
    router: APIRouter,
    registry: Type[RouteModelRegistry] | Token[RouteModelRegistry] = RouteModelRegistry,
    tags: bool = True,
) -> None:
    """
    Register all generated routes in the given FastAPI router.

    Args:
        router: The FastAPI router to register the routes in
        registry: Either RouteModelRegistry class or a Token for a registry
        tags: Whether or not to include tags in the generated routes

    Returns:
        A function that registers routes for the given registry
    """

    routers = get_all_generated_routers(registry, tags=tags)

    for prefix, sub_router in routers.items():
        logger.debug(f"Adding model router with prefix: {prefix}")
        router.include_router(sub_router, prefix=prefix)

    registry_instance = get_service(registry)
    mmr = get_service(MetadataModelRegistry)

    for model_cls in list(registry_instance.get_registered_models()):
        mmr.register_model(model_cls)  # type: ignore


def register_admin_api_route_models(router: APIRouter) -> None:
    """
    Register all generated routes in the given FastAPI router for admin-users.

    Args:
        router: The FastAPI router to register the routes in
    """

    register_api_route_models(router, ADMIN_ROUTE_MODEL_REGISTRY_TOKEN, tags=False)


__all__ = [
    "register_api_route_models",
    "register_admin_api_route_models",
]
