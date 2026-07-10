# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
from copy import copy
from functools import cache
from typing import get_origin, Literal, Union, get_args, Any, cast

from pydantic import BaseModel as PydanticBaseModel, ConfigDict, RootModel
from pydantic_core import PydanticUndefined
from edgy.core.db.fields.types import BaseFieldType

from fastedgy.schemas import create_model
from fastedgy.models.base import BaseModel, BaseView


class RelationOperation(
    RootModel[
        Union[
            tuple[Literal["link"], int],
            tuple[Literal["unlink"], int],
            tuple[Literal["delete"], int],
            tuple[Literal["create"], dict[str, Any]],
            tuple[Literal["update"], dict[str, Any]],
            tuple[Literal["set"], list[int]],
            tuple[Literal["clear"]],
        ]
    ]
):
    """A single advanced-mode relation operation: ``[action, value]`` (or
    ``[action]`` for ``clear``).

    Declared as a shared model so the OpenAPI schema documents each operation
    once (referenced by every relation field) instead of inlining it everywhere.
    """


# Relation input: simple mode (list of ids), advanced mode (list of operations)
# or inline mode (list of objects, each treated as a create operation).
RelationInput = Union[list[int], list[RelationOperation], list[dict[str, Any]]]


class ForeignKeyObject(PydanticBaseModel):
    """Object form of a foreign key input.

    Links the related record identified by ``id``; any extra property updates
    that record in place (link + update). Declared as a shared model so the
    OpenAPI schema documents it once instead of inlining it on every relation.
    """

    model_config = ConfigDict(extra="allow")

    id: int


class ForeignKeyOperation(
    RootModel[
        Union[
            tuple[Literal["link"], int],
            tuple[Literal["unlink"]],
            tuple[Literal["delete"], int],
            tuple[Literal["create"], dict[str, Any]],
            tuple[Literal["update"], dict[str, Any]],
        ]
    ]
):
    """A single advanced-mode foreign key operation: ``[action, value]`` (or
    ``[action]`` for ``unlink``).
    """


# Foreign key input: an id (link), an object (link, plus update with extra
# properties), or a single advanced-mode operation.
ForeignKeyInput = Union[int, ForeignKeyObject, ForeignKeyOperation]


class ReferenceObject(PydanticBaseModel):
    """Polymorphic reference input: the target model metadata name and the
    record id. Declared as a shared model so the OpenAPI schema documents it
    once instead of inlining it on every generic reference field."""

    model: str
    id: int


def _reference_field_options(field_name: str, field: Any) -> dict[str, Any]:
    try:
        targets = ", ".join(f"`{name}`" for name in sorted(field.targets().keys()))
    except ValueError:
        targets = ""

    description = f'Polymorphic reference for {field_name}: `{{"model": ..., "id": ...}}`.' + (
        f"\n\nAllowed models: {targets}" if targets else ""
    )
    return {
        "description": description,
        "examples": [{"model": "task", "id": 5}],
    }


def _foreign_key_field_options(field_name: str) -> dict[str, Any]:
    return {
        "description": (
            f"Foreign key for {field_name}.\n\n"
            f"**Link by id:** `5`\n\n"
            f'**Link by object:** `{{"id": 5}}`\n\n'
            f'**Link and update:** `{{"id": 5, "name": "New"}}`\n\n'
            f"**Unlink:** `null`\n\n"
            f'**Advanced mode:** a single operation `["action", value]`\n\n'
            f"Available actions:\n"
            f"- `create` - Create a new record and link (value=object)\n"
            f"- `update` - Update the record and link (value={{id:X,...}})\n"
            f"- `link` - Link an existing record (value=id)\n"
            f"- `unlink` - Remove the link (no value)\n"
            f"- `delete` - Delete the record and remove the link (value=id)"
        ),
        "examples": [
            5,
            {"id": 5},
            {"id": 5, "name": "New"},
            ["link", 5],
            ["create", {"name": "New"}],
            ["unlink"],
        ],
    }


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


@cache
def generate_input_create_model[M: BaseModel | BaseView](model_cls: type[M]) -> type[M]:
    """Generate Pydantic input model for POST with M2M/O2M support."""
    from fastedgy.schemas import Field as PydanticField
    from fastedgy.api_route_model.action.relations import is_exposed_relation_field
    from edgy.core.db.fields.foreign_keys import ForeignKey

    fields = {}

    for field_name, field_info in model_cls.model_fields.items():
        field = cast(BaseFieldType, field_info)

        # Skip primary keys and read-only fields
        if field.read_only or field.primary_key:
            continue

        # Detect M2M or O2M fields (include them even if excluded)
        if is_exposed_relation_field(field):
            # Accept either:
            # - list[int] (simple: [1,2,3] → [["set", [1,2,3]]])
            # - list[list] (advanced: [["create", {...}], ["link", 42]])
            # Using Any for advanced mode to keep OpenAPI schema simple
            field_type = optional_field_type(RelationInput) if field.null else RelationInput

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
        elif getattr(field, "is_generic_foreign_key", False):
            # Polymorphic reference: a {model, id} object (nullable when the
            # relation is nullable, optional when the exposed column pair is
            # writable — the action then requires one of the two forms).
            options = _reference_field_options(field_name, field)
            if getattr(field, "relation_nullable", True) or getattr(field, "expose_columns", "none") == "write":
                fields[field_name] = (
                    Union[ReferenceObject, None],
                    PydanticField(default=None, **options),
                )
            else:
                fields[field_name] = (ReferenceObject, PydanticField(**options))
        elif isinstance(field, ForeignKey) and not field.exclude:
            # ForeignKey accepts an id, an object ({"id": ...} with optional
            # updates) or a single advanced-mode operation.
            options = _foreign_key_field_options(field_name)
            if field.null:
                fields[field_name] = (
                    Union[ForeignKeyInput, None],
                    PydanticField(default=None, **options),
                )
            else:
                fields[field_name] = (ForeignKeyInput, PydanticField(**options))
        elif not field.exclude:
            # Regular scalar field (only if not excluded)
            field_type = field.field_type
            if field.null:
                field_type = optional_field_type(field.field_type)

            field_to_use = field

            # An exposed generic column stays optional even when non-nullable:
            # the pair may come through the reference object instead, and the
            # action cross-validates the two forms.
            if getattr(field, "is_generic_column", False) and not field.null:
                field_to_use = copy(field)
                setattr(field_to_use, "required", False)
                field_to_use.null = True
                field_to_use.default = None
                setattr(field_to_use, "default_factory", None)
                field_type = optional_field_type(field.field_type)

            # A non-JSON-serializable literal default (auto_now/auto_now_add on a
            # writable field renders as functools.partial) would leak into the
            # input schema and trip Pydantic's schema serializer. Drop it: the
            # field stays optional and the ORM still applies its default at save
            # time (the action uses exclude_unset). default_factory is left as-is,
            # since Pydantic never serializes it into the schema.
            default = getattr(field, "default", PydanticUndefined)
            if default is not PydanticUndefined and default is not None and not _is_json_serializable(default):
                field_to_use = copy(field)
                field_to_use.default = None
                field_type = optional_field_type(field.field_type)

            fields[field_name] = (field_type, field_to_use)

    return cast(type[M], create_model(f"{model_cls.__name__}-Create", **fields))


@cache
def generate_input_patch_model[M: BaseModel | BaseView](model_cls: type[M]) -> type[M]:
    """Generate Pydantic input model for PATCH with M2M/O2M support."""
    from fastedgy.schemas import Field as PydanticField
    from fastedgy.api_route_model.action.relations import is_exposed_relation_field
    from edgy.core.db.fields.foreign_keys import ForeignKey

    fields = {}

    for field_name, field_info in model_cls.model_fields.items():
        field = cast(BaseFieldType, field_info)

        # Skip primary keys and read-only fields
        if field.read_only or field.primary_key:
            continue

        # Detect M2M or O2M fields (include them even if excluded)
        if is_exposed_relation_field(field):
            # Accept either:
            # - list[int] (simple: [1,2,3] → [["set", [1,2,3]]])
            # - list[list] (advanced: [["clear"], ["create", {...}], ["link", 42]])
            # Using list[list] for advanced mode to keep OpenAPI schema simple
            fields[field_name] = (
                Union[RelationInput, None],
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
        elif getattr(field, "is_generic_foreign_key", False):
            # Polymorphic reference: a {model, id} object or null to unlink.
            fields[field_name] = (
                Union[ReferenceObject, None],
                PydanticField(default=None, **_reference_field_options(field_name, field)),
            )
        elif isinstance(field, ForeignKey) and not field.exclude:
            # ForeignKey accepts an id, an object ({"id": ...} with optional
            # updates), null to unlink, or a single advanced-mode operation.
            fields[field_name] = (
                Union[ForeignKeyInput, None],
                PydanticField(default=None, **_foreign_key_field_options(field_name)),
            )
        elif not field.exclude:
            # Regular scalar field (only if not excluded)
            py_field = copy(field)
            setattr(py_field, "required", False)
            py_field.null = True
            py_field.default = None
            # A PATCH body is fully optional (applied with exclude_unset), so a
            # field's default_factory is irrelevant here; clearing it also avoids
            # the default + default_factory pair that pydantic forbids and FastAPI
            # rejects when building the OpenAPI schema.
            setattr(py_field, "default_factory", None)
            py_field.field_type = optional_field_type(field.field_type)
            fields[field_name] = (py_field.field_type, py_field)

    return cast(type[M], create_model(f"{model_cls.__name__}-Update", **fields))


def optional_field_type(field_type):
    if get_origin(field_type) is Union:
        args = get_args(field_type)

        if type(None) in args:
            return field_type

        return Union[*args, None]
    else:
        return Union[field_type, None]


def clean_empty_strings(item_data: BaseModel) -> None:
    """Convert empty strings to None in Pydantic model instance."""
    for field_name in item_data.model_fields_set:
        value = getattr(item_data, field_name)
        if value == "":
            setattr(item_data, field_name, None)


__all__ = [
    "RelationOperation",
    "RelationInput",
    "ForeignKeyObject",
    "ForeignKeyOperation",
    "ForeignKeyInput",
    "generate_input_create_model",
    "generate_input_patch_model",
    "optional_field_type",
    "clean_empty_strings",
]
