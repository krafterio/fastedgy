# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from typing import Any, cast

from fastapi import APIRouter

from fastedgy.api_route_model.generator import get_all_generated_routers
from fastedgy.api_route_model.registry import (
    CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelRegistry,
)
from fastedgy.dependencies import Token, get_service
from fastedgy.metadata_model import MetadataModelRegistry

logger = logging.getLogger("api_route_model.router")


def register_api_route_models(
    router: APIRouter,
    registry: type[RouteModelRegistry] | Token[RouteModelRegistry] = RouteModelRegistry,
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

    _resolve_generic_references(registry)
    _refuse_queued_task_routes(registry)

    if registry is RouteModelRegistry:
        _check_scoping(registry)

    routers = get_all_generated_routers(registry, tags=tags)

    for prefix, sub_router in routers.items():
        logger.debug(f"Adding model router with prefix: {prefix}")
        router.include_router(sub_router, prefix=prefix)

    registry_instance = get_service(registry)
    mmr = get_service(MetadataModelRegistry)

    for model_cls in list(registry_instance.get_registered_models()):
        mmr.register_model(model_cls)


def _resolve_generic_references(registry: type[RouteModelRegistry] | Token[RouteModelRegistry]) -> None:
    """Resolve every GenericForeignKey of the registered models before any route
    or input schema is generated (they are cached): all target models are
    imported by now, so the reverse relations get installed on every target."""
    registry_instance = get_service(registry)

    for model_cls in list(registry_instance.get_registered_models()):
        for field in model_cls.meta.fields.values():
            if getattr(field, "is_generic_foreign_key", False):
                try:
                    cast(Any, field).targets()
                except ValueError as e:
                    logger.warning(f"Could not resolve generic reference targets on {model_cls.__name__}: {e}")


def _refuse_queued_task_routes(registry: type[RouteModelRegistry] | Token[RouteModelRegistry]) -> None:
    from fastedgy.models.queued_task import BaseQueuedTask

    for model_cls in list(get_service(registry).get_registered_models()):
        if issubclass(model_cls, BaseQueuedTask):
            raise TypeError(f"{model_cls.__name__} is a queued task, which gets no generated route")

        for name, field in model_cls.meta.fields.items():
            target = getattr(field, "target", None)

            if isinstance(target, type) and issubclass(target, BaseQueuedTask) and not getattr(field, "exclude", False):
                raise TypeError(f"{model_cls.__name__}.{name} leads to a queued task and must be declared exclude=True")


def unscoped_models(registry: type[RouteModelRegistry] | Token[RouteModelRegistry] = RouteModelRegistry) -> list[type]:
    """The registered models nothing scopes: no applicable global filter (the
    workspace one included), no access guard, and no ``Meta.global_records``."""
    from fastedgy.orm.access_guard import ModelAccessGuardRegistry
    from fastedgy.orm.filter import GlobalFilterRegistry

    filters = get_service(GlobalFilterRegistry)
    guards = get_service(ModelAccessGuardRegistry)

    return [
        model_cls
        for model_cls in get_service(registry).get_registered_models()
        if not getattr(getattr(model_cls, "Meta", None), "global_records", False)
        and not filters.has_applicable_filters(model_cls)
        and not guards.has_guards(model_cls)
    ]


def _check_scoping(registry: type[RouteModelRegistry] | Token[RouteModelRegistry]) -> None:
    from fastedgy.config import BaseSettings

    mode = get_service(BaseSettings).api_scoping_check

    if mode == "off":
        return

    names = sorted(model_cls.__name__ for model_cls in unscoped_models(registry))

    if not names:
        return

    message = f"Generated routes on models nothing scopes (declare Meta.global_records if intended): {', '.join(names)}"

    if mode == "error":
        raise TypeError(message)

    logger.warning(message)


def register_console_api_route_models(router: APIRouter) -> None:
    """
    Register all generated routes in the given FastAPI router for the console.

    Args:
        router: The FastAPI router to register the routes in
    """

    register_api_route_models(router, CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN, tags=False)


# Deprecated alias — use `register_console_api_route_models`. Kept for backward compatibility.
register_admin_api_route_models = register_console_api_route_models


__all__ = [
    "register_admin_api_route_models",
    "register_api_route_models",
    "register_console_api_route_models",
    "unscoped_models",
]
