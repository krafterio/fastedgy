# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod
from typing import Type

from fastapi import APIRouter

from fastedgy.api_route_model.registry import (
    RouteModelOptions,
    RouteModelActionOptions,
    TypeModel,
)


class BaseApiRouteAction(ABC):
    """Base class for all route actions."""

    name: str = ""

    default_options: bool | RouteModelActionOptions = True

    @classmethod
    @abstractmethod
    def register_route(
        cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions
    ) -> None:
        """
        Register this action's route to the FastAPI router.

        Args:
            router: The FastAPI router to add the route to
            model_cls: The Edgy model class
            options: Configuration options for this route
        """
        pass

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

    _actions: dict[str, Type[BaseApiRouteAction]] = {}

    def register_action(self, action_cls: Type[BaseApiRouteAction]) -> None:
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

    def get_action(self, name: str) -> Type[BaseApiRouteAction]:
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

    def get_all_actions(self) -> dict[str, Type[BaseApiRouteAction]]:
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


__all__ = [
    "BaseApiRouteAction",
    "ApiRouteActionRegistry",
]
