# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod
from copy import copy
from typing import Type, get_origin, Union, get_args, Any

from fastapi import APIRouter
from pydantic import create_model

from fastedgy.api_route_model.registry import (
    RouteModelOptions,
    RouteModelActionOptions,
    TypeModel,
)


def generate_output_model[M = TypeModel](model_cls: M) -> type[M]:
    from pydantic import Field as PydanticField

    fields = {}

    for field_name, field in model_cls.model_fields.items():
        if not field.exclude:
            fields[field_name] = (field.field_type, field)
        elif is_many_to_many_field(field) or is_one_to_many_field(field):
            fields[field_name] = (
                list[dict[str, Any]] | None,
                PydanticField(default=None, exclude=False)
            )

    return create_model(f"{model_cls.__name__}", **fields)


def generate_input_create_model[M = TypeModel](model_cls: M) -> type[M]:
    """Generate Pydantic input model for POST with M2M/O2M support."""
    from pydantic import Field as PydanticField

    fields = {}

    for field_name, field in model_cls.model_fields.items():
        # Skip primary keys and read-only fields
        if field.read_only or field.primary_key:
            continue

        # Detect M2M or O2M fields (include them even if excluded)
        if is_many_to_many_field(field) or is_one_to_many_field(field):
            # Accept either:
            # - list[int] (simple: [1,2,3] → [["set", [1,2,3]]])
            # - list[list] (advanced: [["create", {...}], ["link", 42]])
            # Using Any for advanced mode to keep OpenAPI schema simple
            field_type = (
                optional_field_type(Union[list[int], list[list]])
                if field.null
                else Union[list[int], list[list]]
            )

            fields[field_name] = (
                field_type,
                PydanticField(
                    default=[] if not field.null else None,
                    description=(
                        f"Relations for {field_name}.\n\n"
                        f"**Simple mode:** Array of IDs: `[1, 2, 3]`\n\n"
                        f'**Advanced mode:** Array of operations `[["action", value], ...]`\n\n'
                        f"Available actions:\n"
                        f"- `create` - Create new record and link (value=object)\n"
                        f"- `update` - Update record and ensure link (value={{id:X,...}})\n"
                        f"- `link` - Link existing record (value=id)\n"
                        f"- `unlink` - Remove link without deleting (value=id)\n"
                        f"- `delete` - Delete record and remove link (value=id)\n"
                        f"- `set` - Replace all links (value=[ids])\n"
                        f"- `clear` - Remove all links (no value)"
                    ),
                    examples=[
                        [1, 2, 3],
                        [["link", 1], ["create", {"name": "New"}]],
                        [["clear"], ["set", [1, 2, 3]]],
                    ],
                ),
            )
        elif not field.exclude:
            # Regular scalar field (only if not excluded)
            field_type = field.field_type
            if field.null:
                field_type = optional_field_type(field.field_type)
            fields[field_name] = (field_type, field)

    return create_model(f"{model_cls.__name__}Create", **fields)


def generate_input_patch_model[M = TypeModel](model_cls: M) -> type[M]:
    """Generate Pydantic input model for PATCH with M2M/O2M support."""
    from pydantic import Field as PydanticField

    fields = {}

    for field_name, field in model_cls.model_fields.items():
        # Skip primary keys and read-only fields
        if field.read_only or field.primary_key:
            continue

        # Detect M2M or O2M fields (include them even if excluded)
        if is_many_to_many_field(field) or is_one_to_many_field(field):
            # Accept either:
            # - list[int] (simple: [1,2,3] → [["set", [1,2,3]]])
            # - list[list] (advanced: [["clear"], ["create", {...}], ["link", 42]])
            # Using list[list] for advanced mode to keep OpenAPI schema simple
            fields[field_name] = (
                Union[list[int], list[list], None],
                PydanticField(
                    default=None,
                    description=(
                        f"Relations for {field_name}.\n\n"
                        f"**Simple mode:** Array of IDs: `[1, 2, 3]`\n\n"
                        f'**Advanced mode:** Array of operations `[["action", value], ...]`\n\n'
                        f"Available actions:\n"
                        f"- `create` - Create new record and link (value=object)\n"
                        f"- `update` - Update record and ensure link (value={{id:X,...}})\n"
                        f"- `link` - Link existing record (value=id)\n"
                        f"- `unlink` - Remove link without deleting (value=id)\n"
                        f"- `delete` - Delete record and remove link (value=id)\n"
                        f"- `set` - Replace all links (value=[ids])\n"
                        f"- `clear` - Remove all links (no value)"
                    ),
                    examples=[
                        [1, 2, 3],
                        [["link", 1], ["create", {"name": "New"}]],
                        [["clear"], ["set", [1, 2, 3]]],
                    ],
                ),
            )
        elif not field.exclude:
            # Regular scalar field (only if not excluded)
            py_field = copy(field)
            py_field.required = False
            py_field.null = True
            py_field.default = None
            py_field.field_type = optional_field_type(field.field_type)
            fields[field_name] = (py_field.field_type, py_field)

    return create_model(f"{model_cls.__name__}Update", **fields)


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


def is_many_to_many_field(field) -> bool:
    """
    Check if a field is a ManyToMany field.

    Args:
        field: The field to check

    Returns:
        True if the field is a ManyToMany field, False otherwise
    """
    return getattr(field, "is_m2m", False) is True


def is_one_to_many_field(field) -> bool:
    """
    Check if a field is a reverse ForeignKey (One2Many).

    Args:
        field: The field to check

    Returns:
        True if the field is a One2Many field, False otherwise

    Note:
        Currently not implemented - One2Many support to be added later.
    """
    # TODO: Implement O2M detection based on Edgy's reverse FK
    return False


def get_related_model(field) -> type:
    """
    Extract the related model class from a relational field.

    Args:
        field: A ManyToMany or ForeignKey field

    Returns:
        The related model class

    Raises:
        AttributeError: If the field doesn't have a 'target' attribute
    """
    # For M2M and FK fields, the 'target' property resolves the related model
    return field.target


__all__ = [
    "generate_output_model",
    "generate_input_create_model",
    "generate_input_patch_model",
    "optional_field_type",
    "clean_empty_strings",
    "BaseApiRouteAction",
    "ApiRouteActionRegistry",
    "is_many_to_many_field",
    "is_one_to_many_field",
    "get_related_model",
]
