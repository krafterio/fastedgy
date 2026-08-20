# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from functools import cache
from typing import Any, cast

from sqlalchemy import Boolean, Date, DateTime, Float, Integer

EXTRA_FIELD_PREFIX = "extra_"


@cache
def _extra_sql_types() -> dict[Any, Any]:
    from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType

    return {
        WorkspaceExtraFieldType.boolean: Boolean,
        WorkspaceExtraFieldType.date: Date,
        WorkspaceExtraFieldType.datetime: DateTime(timezone=True),
        WorkspaceExtraFieldType.float: Float,
        WorkspaceExtraFieldType.integer: Integer,
    }


def has_extra_fields(model_cls: Any) -> bool:
    return "extra" in model_cls.meta.fields


def declared_extra_fields(model_cls: Any) -> dict[str, Any]:
    if not has_extra_fields(model_cls):
        return {}

    from fastedgy import context
    from fastedgy.metadata_model.generator import generate_metadata_name

    return context.get_map_workspace_extra_fields(generate_metadata_name(model_cls))


def extra_field_column(model_cls: Any, field_path: str) -> Any | None:
    """The SQL expression reading `extra_<name>` out of the JSON column.

    ``->>`` always yields text, so the column is cast to the type the workspace
    declared — otherwise a comparison against an already-converted value fails
    outright (``text = integer``), and ordering would put "10" before "2"."""
    from sqlalchemy import cast as sa_cast

    from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType

    if "." in field_path or not field_path.startswith(EXTRA_FIELD_PREFIX):
        return None

    declared = declared_extra_fields(model_cls)
    name = field_path[len(EXTRA_FIELD_PREFIX) :]

    if name not in declared:
        return None

    column = model_cls.columns.extra.op("->>")(name)
    sql_type = _extra_sql_types().get(cast(WorkspaceExtraFieldType, declared[name].field_type))

    return column if sql_type is None else sa_cast(column, sql_type)


def pop_extra_field_values(model_cls: Any, data: dict[str, Any]) -> dict[str, Any]:
    from fastapi import HTTPException

    keys = [key for key in data if key.startswith(EXTRA_FIELD_PREFIX)]

    if not keys:
        return {}

    declared = declared_extra_fields(model_cls)
    values: dict[str, Any] = {}

    for key in keys:
        name = key[len(EXTRA_FIELD_PREFIX) :]
        value = data.pop(key)

        if name not in declared:
            raise HTTPException(status_code=422, detail=f"Unknown extra field '{key}'")

        values[name] = value

    return values


def merge_extra_field_values(current: Any, values: dict[str, Any]) -> dict[str, Any]:
    return {**(current or {}), **values}


__all__ = [
    "EXTRA_FIELD_PREFIX",
    "declared_extra_fields",
    "extra_field_column",
    "has_extra_fields",
    "merge_extra_field_values",
    "pop_extra_field_values",
]
