# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import Model
from fastedgy.orm.filter.types import (
    InvalidFilterError,
    FilterRule,
    FilterCondition,
    Filter,
    And,
    Or,
)
from fastedgy.orm.filter.operators import get_filter_operators
from fastedgy.orm.filter.utils import is_rule, is_condition


def validate_filters(
    model_cls: type[Model], filters: Filter | None
) -> FilterCondition | None:
    if not filters:
        return None

    # Filter Rule
    if is_rule(filters):
        if not validate_filter_field(model_cls, filters.field):
            raise InvalidFilterError(f"Invalid filter field: {filters.field}")

        if not validate_filter_operator(model_cls, filters.field, filters.operator):
            raise InvalidFilterError(
                f"Invalid operator {filters.operator} for field {filters.field}"
            )

        return filters

    # Filter Condition
    if is_condition(filters):
        validated_rules = []

        for rule in filters.rules:
            validated_rule = validate_filters(model_cls, rule)

            if validated_rule:
                validated_rules.append(validated_rule)

        if validated_rules:
            if filters.condition == "&":
                return And(*validated_rules)
            else:
                return Or(*validated_rules)

    raise InvalidFilterError("Invalid filter expression")


def validate_filter_field(model_cls: type[Model], field_path: str) -> bool:
    if not field_path:
        return False

    if field_path.startswith("extra_"):
        from fastedgy.metadata_model.generator import generate_metadata_name
        from fastedgy import context

        if "extra" not in model_cls.meta.fields:
            return False

        extra_field_name = field_path[6:]
        extra_fields = context.get_map_workspace_extra_fields(
            generate_metadata_name(model_cls)
        )

        return extra_field_name in extra_fields

    parts = field_path.split(".")
    current_cls = model_cls

    for i, part in enumerate(parts):
        if part not in current_cls.meta.fields:
            return False

        field_info = current_cls.meta.fields.get(part)

        if i < len(parts) - 1:
            if hasattr(field_info, "target"):
                current_cls = field_info.target
            elif hasattr(field_info, "related_from"):
                current_cls = field_info.related_from
            else:
                return False

    return True


def validate_filter_operator(
    model_cls: type[Model], field_path: str, operator: str
) -> bool:
    if not field_path or not operator:
        return False

    if field_path.startswith("extra_"):
        from fastedgy.models.workspace_extra_field import (
            EXTRA_FIELDS_MAP,
            EXTRA_FIELD_TYPE_OPTIONS,
        )
        from fastedgy.metadata_model.generator import generate_metadata_name
        from fastedgy import context

        if "extra" not in model_cls.meta.fields:
            return False

        extra_field_name = field_path[6:]
        extra_fields = context.get_map_workspace_extra_fields(
            generate_metadata_name(model_cls)
        )

        if extra_field_name not in extra_fields:
            return False

        extra_field = extra_fields[extra_field_name]
        field_type = EXTRA_FIELDS_MAP.get(extra_field.field_type, None)

        if not field_type:
            return False

        ft = field_type(**EXTRA_FIELD_TYPE_OPTIONS[extra_field.field_type])

        return get_filter_operators(ft)

    parts = field_path.split(".")
    current_cls = model_cls

    for i, part in enumerate(parts):
        if part not in current_cls.meta.fields:
            return False

        field_info = current_cls.meta.fields.get(part)

        if i < len(parts) - 1:
            if hasattr(field_info, "target"):
                current_cls = field_info.target
            elif hasattr(field_info, "related_from"):
                current_cls = field_info.related_from
            else:
                return False
        else:
            return operator in get_filter_operators(field_info)

    return False


__all__ = [
    "validate_filters",
    "validate_filter_field",
    "validate_filter_operator",
]
