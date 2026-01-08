# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
from copy import copy
from typing import get_origin, Union, get_args, Any, TypeVar

from fastedgy.schemas import create_model
from fastedgy.api_route_model.registry import TypeModel

M = TypeVar("M", bound=TypeModel)


def generate_output_model(model_cls: M) -> type[M]:
    from fastedgy.schemas import Field as PydanticField
    from fastedgy.api_route_model.action.relations import is_relation_field
    from edgy.core.db.fields.foreign_keys import ForeignKey

    fields = {}

    for field_name, field in model_cls.model_fields.items():
        if not field.exclude:
            field_type = field.field_type
            field_to_use = field

            # ForeignKey fields are serialized as dicts by model_dump()
            # It is required to accept both the model type and dict[str, Any]
            if isinstance(field, ForeignKey):
                if get_origin(field_type) is Union:
                    args = get_args(field_type)
                    # Add dict[str, Any] to the union if not already present
                    if dict not in args and not any(
                        get_origin(arg) is dict for arg in args
                    ):
                        field_type = Union[*args, dict[str, Any]]
                else:
                    field_type = Union[field_type, dict[str, Any]]

            # Remove default_factory from output schema if not JSON serializable
            # Required to avoid empty values ​​in API responses in case of a serialization warning
            if hasattr(field, "default_factory") and field.default_factory is not None:
                try:
                    json.dumps(field.default_factory)
                except (TypeError, ValueError):
                    # default_factory is not JSON serializable, remove it from output schema
                    field_to_use = copy(field)
                    field_to_use.default_factory = None
                    field_to_use.default = None

            fields[field_name] = (field_type, field_to_use)
        elif is_relation_field(field):
            fields[field_name] = (
                list[dict[str, Any]] | None,
                PydanticField(default=None, exclude=False),
            )

    return create_model(f"{model_cls.__name__}", **fields)


def generate_input_create_model(model_cls: M) -> type[M]:
    """Generate Pydantic input model for POST with M2M/O2M support."""
    from fastedgy.schemas import Field as PydanticField
    from fastedgy.api_route_model.action.relations import is_relation_field

    fields = {}

    for field_name, field in model_cls.model_fields.items():
        # Skip primary keys and read-only fields
        if field.read_only or field.primary_key:
            continue

        # Detect M2M or O2M fields (include them even if excluded)
        if is_relation_field(field):
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


def generate_input_patch_model(model_cls: M) -> type[M]:
    """Generate Pydantic input model for PATCH with M2M/O2M support."""
    from fastedgy.schemas import Field as PydanticField
    from fastedgy.api_route_model.action.relations import is_relation_field

    fields = {}

    for field_name, field in model_cls.model_fields.items():
        # Skip primary keys and read-only fields
        if field.read_only or field.primary_key:
            continue

        # Detect M2M or O2M fields (include them even if excluded)
        if is_relation_field(field):
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


__all__ = [
    "generate_output_model",
    "generate_input_create_model",
    "generate_input_patch_model",
    "optional_field_type",
    "clean_empty_strings",
]
