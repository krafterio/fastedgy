# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

import sqlalchemy as sa
from inspect import isclass

from fastedgy.orm import fields, Model
from sqlalchemy.orm import ColumnProperty
from sqlalchemy.orm.attributes import InstrumentedAttribute


def find_primary_key_field(model_cls: type[Model] | Model) -> str | None:
    for field_name, field_info in model_cls.meta.fields.items():
        if hasattr(field_info, "primary_key") and field_info.primary_key:
            return field_name

    if "id" in model_cls.meta.fields:
        return "id"

    return None


def extract_field_names(record: dict, parent_field: str = "") -> list[str]:
    fields = []

    for record_field, record_val in record.items():
        record_field_name = (
            f"{parent_field}.{record_field}" if parent_field else record_field
        )

        if isinstance(record_val, dict):
            fields.extend(extract_field_names(record_val, record_field_name))
        elif isinstance(record_val, list) and len(record_val) > 0 and isinstance(record_val[0], dict):
            fields.extend(extract_field_names(record_val[0], record_field_name))
        else:
            fields.append(record_field_name)

    return fields


def get_columns(mixed):
    """
    Return a list of all Column objects for given SQLAlchemy object.

    The type of the list depends on the type of the object to return the
    columns from.

    ::

        get_columns(User)

        get_columns(User())

        get_columns(User.__table__)

        get_columns(User.__mapper__)

        get_columns(sa.orm.aliased(User))

        get_columns(sa.orm.alised(User.__table__))


    :param mixed:
        SA Table object, SA Mapper, SA declarative class, SA declarative class
        instance or an alias of any of these objects
    """
    if isinstance(mixed, sa.sql.selectable.Selectable):  # type: ignore
        return mixed.selected_columns
    if isinstance(mixed, sa.orm.util.AliasedClass):  # type: ignore
        return sa.inspect(mixed).mapper.columns
    if isinstance(mixed, sa.orm.Mapper):  # type: ignore
        return mixed.columns
    if isinstance(mixed, InstrumentedAttribute):
        return mixed.property.columns
    if isinstance(mixed, ColumnProperty):
        return mixed.columns
    if isinstance(mixed, sa.Column):
        return [mixed]
    if not isclass(mixed):
        mixed = mixed.__class__
    return sa.inspect(mixed).columns


async def get_value_from_path(instance: Model, path: str) -> Any | None:
    async def _resolve(
        obj_or_list: Model | list[Model], path_parts: list[str] | None
    ) -> Any | None:
        if not path_parts:
            return obj_or_list

        key = path_parts[0]
        rest = path_parts[1:]

        if isinstance(obj_or_list, list):
            results = []

            for obj in obj_or_list:
                val = await _resolve(obj, path_parts)

                if isinstance(val, list):
                    results.extend(val)
                else:
                    results.append(val)

            return results

        if not hasattr(obj_or_list, key):
            return None

        value = getattr(obj_or_list, key)
        field = obj_or_list.meta.fields.get(key, None)

        if hasattr(value, "all") and callable(value.all):
            value = await value.all()  # type: ignore

            return await _resolve(value, rest or ["id"])

        if field and isinstance(field, (fields.ForeignKey, fields.ManyToMany)):
            return await _resolve(value, rest or ["id"])

        if rest:
            raise ValueError(
                f"Le champ '{key}' n'est pas une relation, impossible de continuer avec '{'.'.join(rest)}'"
            )

        return value

    return await _resolve(instance, path.split("."))


__all__ = [
    "find_primary_key_field",
    "extract_field_names",
    "get_columns",
    "get_value_from_path",
]
