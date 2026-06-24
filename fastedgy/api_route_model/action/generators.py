# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
from copy import copy
from functools import cache
from typing import Callable, get_origin, Literal, Union, get_args, Any, cast

from pydantic import RootModel
from pydantic_core import PydanticUndefined
from edgy.core.db.fields.types import BaseFieldType

from fastedgy.schemas import create_model
from fastedgy.models.base import BaseModel


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


# Relation input: simple mode (list of ids) or advanced mode (list of operations).
RelationInput = Union[list[int], list[RelationOperation]]


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def _has_unserializable_default(field: BaseFieldType) -> bool:
    factory = getattr(field, "default_factory", None)

    if factory is not None and not _is_json_serializable(factory):
        return True

    default = getattr(field, "default", PydanticUndefined)

    return default is not PydanticUndefined and not _is_json_serializable(default)


_output_model_cache: dict[type, type] = {}
_output_model_building: set[type] = set()


def generate_output_model[M: BaseModel](model_cls: type[M]) -> type[M]:
    from fastedgy.schemas import Field as PydanticField
    from fastedgy.api_route_model.action.relations import is_exposed_relation_field
    from edgy.core.db.fields.foreign_keys import ForeignKey

    cached = _output_model_cache.get(model_cls)
    if cached is not None:
        return cast(type[M], cached)

    # A foreign key can point back to a model whose output is still being built
    # (self-references such as parent/parent_task). Break the cycle with a string
    # forward reference, resolved by model_rebuild() once the class exists.
    if model_cls in _output_model_building:
        return cast(type[M], model_cls.__name__)

    _output_model_building.add(model_cls)

    try:
        fields = {}

        for field_name, field_info in model_cls.model_fields.items():
            field = cast(BaseFieldType, field_info)

            if not field.exclude:
                field_type = field.field_type
                field_to_use = field

                # A ForeignKey is serialized either as the related model (when its
                # fields are expanded) or as a partial object ({"id": ...} by
                # default, or the selected fields with X-Fields), and as null when
                # the relation is optional.
                if isinstance(field, ForeignKey):
                    related_output = generate_output_model(field.target)
                    if field.null:
                        field_type = Union[related_output, dict[str, Any], None]
                    else:
                        field_type = Union[related_output, dict[str, Any]]

                # Drop non-JSON-serializable defaults (auto_now/auto_now_add render as
                # functools.partial, default_factory callables, ...) from the output schema
                if _has_unserializable_default(field):
                    field_to_use = copy(field)
                    field_to_use.default = None
                    setattr(field_to_use, "default_factory", None)

                fields[field_name] = (field_type, field_to_use)
            elif is_exposed_relation_field(field):
                fields[field_name] = (
                    list[dict[str, Any]] | None,
                    PydanticField(default=None, exclude=False),
                )

        model = cast(type[M], create_model(f"{model_cls.__name__}", **fields))
        model.model_rebuild()
        _output_model_cache[model_cls] = model
    finally:
        _output_model_building.discard(model_cls)

    return model


@cache
def generate_input_create_model[M: BaseModel](model_cls: type[M]) -> type[M]:
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
        elif isinstance(field, ForeignKey) and not field.exclude:
            # ForeignKey is set on input with the related record id.
            if field.null:
                fields[field_name] = (int | None, PydanticField(default=None))
            else:
                fields[field_name] = (int, PydanticField())
        elif not field.exclude:
            # Regular scalar field (only if not excluded)
            field_type = field.field_type
            if field.null:
                field_type = optional_field_type(field.field_type)
            fields[field_name] = (field_type, field)

    return cast(type[M], create_model(f"{model_cls.__name__}Create", **fields))


@cache
def generate_input_patch_model[M: BaseModel](model_cls: type[M]) -> type[M]:
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
        elif isinstance(field, ForeignKey) and not field.exclude:
            # ForeignKey is set on input with the related record id.
            fields[field_name] = (int | None, PydanticField(default=None))
        elif not field.exclude:
            # Regular scalar field (only if not excluded)
            py_field = copy(field)
            setattr(py_field, "required", False)
            py_field.null = True
            py_field.default = None
            py_field.field_type = optional_field_type(field.field_type)
            fields[field_name] = (py_field.field_type, py_field)

    return cast(type[M], create_model(f"{model_cls.__name__}Update", **fields))


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


def route_body_model[F: Callable[..., Any]](model: type[BaseModel], param: str = "item_data") -> Callable[[F], F]:
    """Attach a dynamically generated request body model to a route endpoint.

    FastAPI derives the request body schema from the parameter annotation, but a
    runtime-generated model (``generate_input_create_model`` / ``generate_input_patch_model``)
    cannot live in annotation position. This decorator sets it on ``__annotations__``
    so FastAPI reads it, while the static annotation stays a plain type.

    It is the request-body counterpart of FastAPI's native ``response_model=``.
    """

    def decorator(func: F) -> F:
        func.__annotations__[param] = model
        return func

    return decorator


__all__ = [
    "generate_output_model",
    "generate_input_create_model",
    "generate_input_patch_model",
    "optional_field_type",
    "clean_empty_strings",
    "route_body_model",
]
