# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod
from copy import copy
from typing import Type, get_origin, Union, get_args, Any

from fastapi import APIRouter
from fastedgy.dependencies import register_service
from pydantic import create_model

from fastedgy.api_route_model.registry import RouteModelOptions, RouteModelActionOptions, TypeModel


def generate_output_model[M = TypeModel](model_cls: M) -> type[M]:
    fields = {}

    for field_name, field in model_cls.model_fields.items():
        if not field.exclude:
            fields[field_name] = (field.field_type, field)

    return create_model(f'{model_cls.__name__}', **fields)


def generate_input_create_model[M = TypeModel](model_cls: M) -> type[M]:
    fields = {}

    for field_name, field in model_cls.model_fields.items():
        if not field.exclude and not field.read_only and not field.primary_key:
            field_type = field.field_type
            if field.null:
                field_type = optional_field_type(field.field_type)
            fields[field_name] = (field_type, field)

    return create_model(f'{model_cls.__name__}-Input', **fields)


def generate_input_patch_model[M = TypeModel](model_cls: M) -> type[M]:
    fields = {}

    for field_name, field in model_cls.model_fields.items():
        if not field.exclude and not field.read_only and not field.primary_key:
            py_field = copy(field)
            py_field.required = False
            py_field.null = True
            py_field.default = None
            py_field.field_type = optional_field_type(field.field_type)
            fields[field_name] = (py_field.field_type, py_field)

    return create_model(f'{model_cls.__name__}-InputUpdate', **fields)


def optional_field_type(field_type):
    if get_origin(field_type) is Union:
        args = get_args(field_type)

        if type(None) in args:
            return field_type

        return Union[*args, None]
    else:
        return Union[field_type, None]


def clean_empty_strings(item_data) -> None:
    """Convert empty strings to None in Pydantic model instance."""
    for field_name in item_data.model_fields_set:
        value = getattr(item_data, field_name)
        if value == "":
            setattr(item_data, field_name, None)


class BaseApiRouteAction(ABC):
    """Base class for all route actions."""

    name: str = ""

    default_options: bool | RouteModelActionOptions = True

    @classmethod
    @abstractmethod
    def register_route(
            cls,
            router: APIRouter,
            model_cls: TypeModel,
            options: RouteModelActionOptions
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


register_service(ApiRouteActionRegistry())


__all__ = [
    "generate_output_model",
    "generate_input_create_model",
    "generate_input_patch_model",
    "optional_field_type",
    "clean_empty_strings",
    "BaseApiRouteAction",
    "ApiRouteActionRegistry",
]
