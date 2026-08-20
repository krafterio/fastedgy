# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable
from typing import Any, cast

from fastedgy.orm.filter.types import (
    And,
    Filter,
    FilterCondition,
    FilterConditionTuple,
    FilterRule,
    FilterRuleTuple,
    FilterTuple,
)


def is_rule(item: Any) -> bool:
    if isinstance(item, FilterRule):
        return True

    return (
        (isinstance(item, (tuple, list)))
        and 2 <= len(item) <= 3
        and isinstance(item[0], str)
        and isinstance(item[1], str)
    )


def is_condition(item: Any) -> bool:
    if isinstance(item, FilterCondition):
        return True

    return (
        (isinstance(item, (tuple, list))) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], list)
    )


def merge_filters(*filters: Filter) -> FilterCondition | None:
    from fastedgy.orm.filter.parser import (
        parse_filter_input_str,
        parse_filter_input_tuple,
    )

    parsed_filters = []

    for filter_item in filters:
        if filter_item is None:
            continue

        if isinstance(filter_item, str):
            parsed = parse_filter_input_str(filter_item)

            if parsed:
                parsed_filters.append(parsed)
        elif isinstance(filter_item, (tuple, list)):
            parsed = parse_filter_input_tuple(cast(FilterTuple, filter_item))

            if parsed:
                parsed_filters.append(parsed)
        elif isinstance(filter_item, (FilterRule, FilterCondition)):
            parsed_filters.append(filter_item)

    if not parsed_filters:
        return None

    if len(parsed_filters) == 1:
        if isinstance(parsed_filters[0], FilterCondition):
            return parsed_filters[0]
        else:
            return And(parsed_filters[0])

    return And(*parsed_filters)


def add_prefix_on_fields(field_prefix: str, filters: list | FilterTuple | None) -> FilterTuple | None:
    from fastedgy.orm.filter.parser import parse_filter_input_array_to_tuple

    if not filters:
        return None

    if isinstance(filters, list):
        filters = parse_filter_input_array_to_tuple(filters)

    if is_rule(filters):
        field, operator, value = cast(FilterRuleTuple, filters)

        return f"{field_prefix}.{field}", operator, value

    elif is_condition(filters):
        condition, rules = cast(FilterConditionTuple, filters)
        new_rules = []

        for rule in rules:
            new_rules.append(add_prefix_on_fields(field_prefix, rule))

        return cast(FilterConditionTuple, (condition, new_rules))

    elif isinstance(filters, list):
        return cast(FilterTuple, [add_prefix_on_fields(field_prefix, item) for item in filters])

    return filters


def _has_relation_filter(filters: Filter | None) -> bool:
    """Check if filters contain relations (field with dot notation)."""
    if not filters:
        return False

    if isinstance(filters, FilterRule):
        return "." in filters.field

    if isinstance(filters, FilterCondition):
        return any(_has_relation_filter(rule) for rule in filters.rules)

    if isinstance(filters, list):
        return any(_has_relation_filter(item) for item in filters)

    return False


def _has_duplicating_relation_filter(model_cls: Any, filters: Filter | None) -> bool:
    """
    Check if filters contain relations that can create duplicate rows.
    Only ManyToMany and OneToMany relations can create duplicates.
    ForeignKey and OneToOne are N:1 or 1:1 relationships, no duplicates possible.
    """
    from fastedgy.orm.fields import ForeignKey, ManyToMany, OneToOne

    if not filters:
        return False

    if isinstance(filters, FilterRule):
        if "." not in filters.field:
            return False

        relation_name = filters.field.split(".")[0]

        if relation_name.startswith("extra_"):
            return False

        field_type = model_cls.meta.fields.get(relation_name)

        if field_type is None:
            return False

        if isinstance(field_type, (ForeignKey, OneToOne)):
            return False

        if isinstance(field_type, ManyToMany):
            return True

        return bool(hasattr(field_type, "related_from"))

    if isinstance(filters, FilterCondition):
        return any(_has_duplicating_relation_filter(model_cls, rule) for rule in filters.rules)

    return False


def has_duplicating_relation_path(model_cls: Any, field_path: str) -> bool:
    """Whether joining ``field_path`` repeats the source record once per related row.

    True as soon as one hop is a reverse one-to-many or a many-to-many: both
    fan out, so the join yields a row per related record instead of per record.
    """
    from fastedgy.orm.fields import ManyToMany

    current_cls = model_cls

    for part in field_path.split(".")[:-1]:
        field_type = current_cls.meta.fields.get(part)

        if field_type is None:
            return False

        if isinstance(field_type, ManyToMany) or hasattr(field_type, "related_from"):
            return True

        if not hasattr(field_type, "target"):
            return False

        current_cls = field_type.target

    return False


def _convert_value(value: Any | None, callback: Callable) -> Any:
    if isinstance(value, str):
        try:
            return callback(value)
        except ValueError:
            return value

    elif isinstance(value, (list, tuple)):
        new_values = []

        for val in value:
            if isinstance(val, str):
                try:
                    val = callback(val)
                except ValueError:
                    pass

            new_values.append(val)

        return new_values

    return value


__all__ = [
    "_convert_value",
    "_has_duplicating_relation_filter",
    "_has_relation_filter",
    "add_prefix_on_fields",
    "has_duplicating_relation_path",
    "is_condition",
    "is_rule",
    "merge_filters",
]
