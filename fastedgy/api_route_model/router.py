# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging

from fastapi import APIRouter
from fastedgy.api_route_model.generator import (
    get_all_generated_routers,
    get_all_generated_admin_routers,
)
from fastedgy.api_route_model.registry import (
    ADMIN_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelRegistry,
)
from fastedgy.dependencies import get_service
from fastedgy.metadata_model import MetadataModelRegistry


logger = logging.getLogger("api_route_model.router")


def register_api_route_models(api_router: APIRouter) -> None:
    """
    Register all generated routes in the FastAPI application.

    Args:
        api_router: The FastAPI router
    """
    # Get all generated routers
    routers = get_all_generated_routers()

    for prefix, router in routers.items():
        logger.debug(f"Adding model router with prefix: {prefix}")
        api_router.include_router(router, prefix=prefix)

    rmr = get_service(RouteModelRegistry)
    mmr = get_service(MetadataModelRegistry)
    for model_cls in list(rmr.get_registered_models()):
        mmr.register_model(model_cls)


def register_admin_api_route_models(api_router: APIRouter) -> None:
    """
    Register all generated routes in the FastAPI application for admin-users.

    Args:
        api_router: The FastAPI router
    """
    # Get all generated routers
    routers = get_all_generated_admin_routers()

    for prefix, router in routers.items():
        logger.debug(f"Adding model router with prefix: {prefix}")
        api_router.include_router(router, prefix=prefix)

    armr = get_service(ADMIN_ROUTE_MODEL_REGISTRY_TOKEN)
    mmr = get_service(MetadataModelRegistry)
    for model_cls in list(armr.get_registered_models()):
        mmr.register_model(model_cls)


__all__ = [
    "logger",
    "register_api_route_models",
    "register_admin_api_route_models",
]
