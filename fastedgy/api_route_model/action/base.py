# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod

from fastapi import APIRouter, HTTPException

from fastedgy.api_route_model.registry import (
    CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelActionOptions,
    RouteModelOptions,
    RouteModelRegistry,
    TypeModel,
)
from fastedgy.dependencies import get_service
from fastedgy.i18n import _t


class BaseApiRouteAction(ABC):
    """Base class for all route actions."""

    name: str = ""

    default_options: bool | RouteModelActionOptions = True

    @classmethod
    @abstractmethod
    def register_route(cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions) -> None:
        """
        Register this action's route to the FastAPI router.

        Args:
            router: The FastAPI router to add the route to
            model_cls: The Edgy model class
            options: Configuration options for this route
        """

    @classmethod
    def should_register(cls, options: RouteModelOptions) -> bool:
        """
        Determine if this action should be registered based on options.

        Args:
            options: Configuration options of route model

        Returns:
            True if this action should be registered, False otherwise
        """
        return bool(options.get(cls.name, cls.default_options))


class ApiRouteActionRegistry:
    """Registry for api route actions."""

    _actions: dict[str, type[BaseApiRouteAction]] = {}

    def register_action(self, action_cls: type[BaseApiRouteAction]) -> None:
        """
        Register an action class.

        Args:
            action_cls: The action class to register

        Raises:
            ValueError: If action name is already registered
        """
        if not action_cls.name:
            raise ValueError(f"Action {action_cls.__name__} must have a non-empty name")

        if action_cls.name in self._actions:
            raise ValueError(f"Action '{action_cls.name}' is already registered")

        self._actions[action_cls.name] = action_cls

    def get_action(self, name: str) -> type[BaseApiRouteAction]:
        """
        Get an action by name.

        Args:
            name: The action name

        Returns:
            The action class

        Raises:
            KeyError: If action name is not registered
        """
        if name not in self._actions:
            raise KeyError(f"Action '{name}' is not registered")

        return self._actions[name]

    def get_all_actions(self) -> dict[str, type[BaseApiRouteAction]]:
        """
        Get all registered actions.

        Returns:
            Dict mapping action names to action classes
        """
        return self._actions

    def get_action_names(self) -> list[str]:
        """
        Get all registered action names.

        Returns:
            List of action names
        """
        return list(self._actions.keys())


async def ensure_action_allowed(model_cls: TypeModel, name: str) -> None:
    """Refuse a generic route that acts on a model the way its generated `name`
    route does, unless that route exists for the caller: in the api registry,
    or in the console one for a sudo caller."""
    from fastedgy.sudo import SudoChecker

    registries = [get_service(RouteModelRegistry)]

    if await get_service(SudoChecker).is_sudo():
        registries.append(get_service(CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN))

    exposed = [registry for registry in registries if registry.is_model_registered(model_cls)]

    if not exposed:
        raise HTTPException(
            status_code=403,
            detail=_t("Model {model_name} is not available", model_name=model_cls.meta.tablename),
        )

    action = get_service(ApiRouteActionRegistry).get_action(name)

    if not any(
        action.should_register(registry.get_model_options(model_cls).get("actions", {})) for registry in exposed
    ):
        raise HTTPException(
            status_code=405,
            detail=_t("Model {model_name} does not allow this action", model_name=model_cls.meta.tablename),
        )


__all__ = [
    "ApiRouteActionRegistry",
    "BaseApiRouteAction",
    "ensure_action_allowed",
]
