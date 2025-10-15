# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, cast

from fastedgy.orm import Model
from fastedgy.orm.fields import (
    BaseFieldType,
    IntegerField,
    DateField,
    DateTimeField,
    DecimalField,
    FloatField,
    ForeignKey,
    ManyToMany,
    OneToOne,
)
from fastedgy.orm.query import QuerySet
from fastedgy.orm.utils import find_primary_key_field
from fastedgy.orm.filter.types import (
    InvalidFilterError,
    FilterRule,
    FilterCondition,
    Filter,
    FilterTuple,
)
from fastedgy.orm.filter.operators import (
    FILTER_OPERATORS_SQL,
    FILTER_DICT_OPERATORS_SQL,
    FILTER_OPERATORS_SQL_UNPACK,
)
from fastedgy.orm.filter.parser import parse_filter_input
from fastedgy.orm.filter.validator import validate_filters
from fastedgy.orm.filter.utils import _has_relation_filter, _convert_value


def build_filter_expression(
    model_cls: type[Model], filters: FilterRule | FilterCondition
) -> Any | None:
    cond_query = cast(
        QuerySet,
        model_cls.global_query
        if hasattr(model_cls, "global_query")
        else model_cls.query,
    )

    if isinstance(filters, FilterRule):
        field = filters.field
        operator_method = FILTER_OPERATORS_SQL.get(filters.operator, None)
        operator_dict_method = FILTER_DICT_OPERATORS_SQL.get(filters.operator, None)

        if not operator_method or not operator_dict_method:
            raise InvalidFilterError(f"Operator '{filters.operator}' is not supported")

        use_col = field.startswith("extra_")
        field_type = _find_field_type_in_model(model_cls, field)

        if isinstance(field_type, ForeignKey):
            field += "." + list(field_type.related_columns.keys())[0]
        elif isinstance(field_type, OneToOne):
            field += "." + list(field_type.related_columns.keys())[0]
        elif isinstance(field_type, ManyToMany):
            field += "." + list(field_type.related_columns.keys())[0]
        elif field_type == "OneToMany":
            field += "." + list(field_type.related_columns.keys())[0]

        column = _find_column_in_model(model_cls, field)
        value = _convert_value_by_field_type(model_cls, field, filters.value)

        if filters.operator in FILTER_OPERATORS_SQL_UNPACK:
            unpack_count = FILTER_OPERATORS_SQL_UNPACK[filters.operator]

            if not isinstance(value, (list, tuple)) or len(value) < unpack_count:
                raise InvalidFilterError(
                    f"Operator '{filters.operator}' requires {unpack_count} values in list"
                )

            return cond_query.and_(
                column.between(*value)
                if use_col
                else operator_dict_method(cond_query, field, value)
            )

        return cond_query.and_(
            operator_method(column, value)
            if use_col
            else operator_dict_method(cond_query, field, value)
        )

    if not filters.rules:
        return None

    expressions = []

    for rule in filters.rules:
        expr = build_filter_expression(model_cls, rule)

        if expr is not None:
            expressions.append(expr)

    if not expressions:
        return None

    if len(expressions) == 1:
        return expressions[0]

    if filters.condition == "|":
        return cond_query.or_(*expressions)

    return cond_query.and_(*expressions)


def filter_query(
    query: QuerySet,
    filters: str | list | FilterTuple | Filter | None,
    restrict_error: bool = False,
) -> QuerySet:
    has_filters = filters is not None

    try:
        if not isinstance(filters, FilterCondition) and not isinstance(
            filters, FilterRule
        ):
            filters = parse_filter_input(filters)

        if not has_filters and not filters:
            return query

        if has_filters and not filters:
            raise InvalidFilterError("Invalid format of filters")

        filters = validate_filters(query.model_class, filters)
    except InvalidFilterError:
        if has_filters and restrict_error:
            primary_key = find_primary_key_field(query.model_class)

            if primary_key:
                return query.filter({f"{primary_key}__is": None})

        raise

    expression = build_filter_expression(query.model_class, filters)

    if expression is not None:
        query = query.filter(expression)

        if _has_relation_filter(filters) and query.distinct_on is None:
            primary_key = find_primary_key_field(query.model_class)
            if primary_key:
                query = query.distinct(primary_key)

    return query


def _find_field_type_in_model(
    model_cls: type[Model], field_path: str
) -> type[BaseFieldType]:
    """
    Recursively find a field type in a model by its field path.

    Args:
        model_cls: The model class to search in
        field_path: The field path (e.g. 'contact.company.name')

    Returns:
        The column object

    Raises:
        InvalidFilterError: If the field path is invalid
    """
    field_parts = field_path.split(".")
    current_model = model_cls

    for i, part in enumerate(field_parts):
        if i == 0 and part.startswith("extra_"):
            from fastedgy.models.workspace_extra_field import EXTRA_FIELDS_MAP
            from fastedgy.metadata_model.generator import generate_metadata_name
            from fastedgy import context

            if "extra" in model_cls.meta.fields:
                extra_field_name = part[6:]
                extra_fields = context.get_map_workspace_extra_fields(
                    generate_metadata_name(current_model)
                )

                if extra_field_name in extra_fields:
                    extra_field = extra_fields[extra_field_name]
                    field_type = EXTRA_FIELDS_MAP.get(extra_field.field_type, None)

                    if field_type:
                        return field_type

            raise InvalidFilterError(
                f"Field '{part}' not found in model {current_model.__name__}"
            )
        elif i == len(field_parts) - 1:
            fields = current_model.meta.fields

            if part in fields:
                return fields.get(part)
            else:
                raise InvalidFilterError(
                    f"Field '{part}' not found in model {current_model.__name__}"
                )
        else:
            if part not in current_model.meta.fields:
                raise InvalidFilterError(
                    f"Field '{part}' not found in model {current_model.__name__}"
                )

            field_info = current_model.meta.fields[part]

            if hasattr(field_info, "related_model"):
                current_model = field_info.related_model
            elif hasattr(field_info, "target"):
                current_model = field_info.target
            elif hasattr(field_info, "related_from"):
                current_model = field_info.related_from
            else:
                raise InvalidFilterError(f"Field '{part}' is not a relationship field")

    raise InvalidFilterError(f"Field '{field_path}' not found")


def _find_column_in_model(model_cls: type[Model], field_path: str) -> Any:
    """
    Recursively find a column in a model by its field path.

    Args:
        model_cls: The model class to search in
        field_path: The field path (e.g. 'contact.company.name')

    Returns:
        The column object

    Raises:
        InvalidFilterError: If the field path is invalid
    """
    field_parts = field_path.split(".")
    current_model = model_cls

    for i, part in enumerate(field_parts):
        if i == 0 and part.startswith("extra_"):
            from fastedgy.models.workspace_extra_field import EXTRA_FIELDS_MAP
            from fastedgy.metadata_model.generator import generate_metadata_name
            from fastedgy import context

            if "extra" in model_cls.meta.fields:
                extra_field_name = part[6:]
                extra_fields = context.get_map_workspace_extra_fields(
                    generate_metadata_name(current_model)
                )

                if extra_field_name in extra_fields:
                    extra_field = extra_fields[extra_field_name]
                    field_type = EXTRA_FIELDS_MAP.get(extra_field.field_type, None)

                    if field_type:
                        return model_cls.columns.extra.op("->>")(extra_field_name)

            raise InvalidFilterError(
                f"Field '{part}' not found in model {current_model.__name__}"
            )
        elif i == len(field_parts) - 1:
            columns = current_model.table.columns  # type: ignore

            if hasattr(columns, part):
                return columns[part]
            else:
                raise InvalidFilterError(
                    f"Field '{part}' not found in model {current_model.__name__}"
                )
        else:
            if part not in current_model.meta.fields:
                raise InvalidFilterError(
                    f"Field '{part}' not found in model {current_model.__name__}"
                )

            field_info = current_model.meta.fields[part]

            if hasattr(field_info, "related_model"):
                current_model = field_info.related_model
            elif hasattr(field_info, "target"):
                current_model = field_info.target
            elif hasattr(field_info, "related_from"):
                current_model = field_info.related_from
            else:
                raise InvalidFilterError(f"Field '{part}' is not a relationship field")

    raise InvalidFilterError(f"Field '{field_path}' not found")


def _convert_value_by_field_type(
    model_cls: type[Model], field_path: str, value: Any
) -> Any:
    """
    Converts a value based on the field type.

    Args:
        model_cls: The model class to search in
        field_path: The field path (e.g. 'contact.company.name')
        value: The value to convert

    Returns:
        The converted value
    """
    field = None
    parts = field_path.split(".")
    current_cls = model_cls

    for part in parts:
        if field_path.startswith("extra_"):
            from fastedgy.metadata_model.generator import generate_metadata_name
            from fastedgy import context
            from fastedgy.models.workspace_extra_field import (
                EXTRA_FIELDS_MAP,
                EXTRA_FIELD_TYPE_OPTIONS,
            )

            extra_field_name = field_path[6:]
            extra_fields = context.get_map_workspace_extra_fields(
                generate_metadata_name(model_cls)
            )

            if extra_field_name in extra_fields:
                extra_field = extra_fields[extra_field_name]
                field_type = EXTRA_FIELDS_MAP.get(extra_field.field_type, None)

                if field_type:
                    field = field_type(
                        **EXTRA_FIELD_TYPE_OPTIONS[extra_field.field_type]
                    )
        else:
            field = current_cls.meta.fields[part]

        if field and hasattr(field, "target"):
            current_cls = field.target
        elif field and hasattr(field, "related_from"):
            current_cls = field.related_from

    if isinstance(field, (DateField, DateTimeField)):
        from datetime import datetime

        return _convert_value(
            value, lambda val: datetime.fromisoformat(val.replace("Z", "+00:00"))
        )
    elif isinstance(field, IntegerField):
        return _convert_value(value, lambda val: int(val))
    elif isinstance(field, (FloatField, DecimalField)):
        return _convert_value(value, lambda val: float(val))

    return value


__all__ = [
    "build_filter_expression",
    "filter_query",
]
