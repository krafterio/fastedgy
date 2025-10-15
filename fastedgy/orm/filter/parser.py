# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, get_args, cast
import json
from urllib.parse import unquote

from fastedgy.orm.filter.types import (
    InvalidFilterError,
    FilterRule,
    FilterCondition,
    FilterTuple,
    FilterRuleTuple,
    FilterConditionTuple,
    FilterConditionType,
    R,
    And,
    Or,
)
from fastedgy.orm.filter.operators import FilterOperator
from fastedgy.orm.filter.utils import is_rule, is_condition


def parse_filter_input(
    filters: str | list | FilterTuple | None,
) -> FilterCondition | None:
    if isinstance(filters, str):
        return parse_filter_input_str(filters)

    if isinstance(filters, list):
        filters = parse_filter_input_array_to_tuple(filters)

    if isinstance(filters, tuple):
        return parse_filter_input_tuple(filters)

    return None


def parse_filter_input_str(filters: str | None) -> FilterCondition | None:
    if not filters:
        return None

    try:
        data = json.loads(unquote(filters))
        tuple_data = parse_filter_input_array_to_tuple(data)

        return parse_filter_input_tuple(tuple_data)
    except json.JSONDecodeError:
        raise InvalidFilterError("Invalid JSON filter expression")


def parse_filter_input_array_to_tuple(filters: list | None) -> FilterTuple | None:
    if not filters:
        return None

    if len(filters) == 0:
        return None

    # Filter Condition
    if is_condition(filters):
        parsed_rules = []

        for rule in filters[1]:
            if isinstance(rule, list):
                parsed_rule = parse_filter_input_array_to_tuple(rule)

                if parsed_rule:
                    parsed_rules.append(parsed_rule)
            else:
                parsed_rules.append(rule)

        return filters[0], parsed_rules

    # Filter Rule
    if is_rule(filters):
        if len(filters) == 2:
            return filters[0], filters[1]
        else:
            return filters[0], filters[1], filters[2]

    # Array Flat: ["|", rule1, rule2, rule3] or ["&", rule1, rule2]
    if len(filters) > 1 and filters[0] in ("&", "|"):
        condition_operator = filters[0]
        parsed_rules = []

        for item in filters[1:]:
            if isinstance(item, list):
                parsed_rule = parse_filter_input_array_to_tuple(item)

                if parsed_rule:
                    parsed_rules.append(parsed_rule)
            else:
                parsed_rules.append(item)

        if parsed_rules:
            return condition_operator, parsed_rules

    # Array List: ["|", [rule1, rule2, rule3]] or ["&", [rule1, rule2]]
    parsed_items = []

    for item in filters:
        if isinstance(item, list):
            parsed_item = parse_filter_input_array_to_tuple(item)

            if parsed_item:
                parsed_items.append(parsed_item)
        else:
            parsed_items.append(item)

    if parsed_items:
        return "&", parsed_items

    raise InvalidFilterError("Invalid filter expression")


def parse_filter_input_tuple(filters: FilterTuple | None) -> FilterCondition | None:
    if not filters:
        return None

    if is_rule(filters):
        rule_tuple = cast(FilterRuleTuple, filters)
        rule = create_rule_from_tuple(rule_tuple)

        return And(rule) if rule else None

    if is_condition(filters):
        condition_tuple = cast(FilterConditionTuple, filters)

        return create_condition_from_tuple(condition_tuple)

    if isinstance(filters, list):
        items = []

        for item in filters:
            if is_rule(item):
                rule = create_rule_from_tuple(cast(FilterRuleTuple, item))

                if rule:
                    items.append(rule)
            elif is_condition(item):
                condition = create_condition_from_tuple(
                    cast(FilterConditionTuple, item)
                )

                if condition:
                    items.append(condition)

        if items:
            return And(*items)

    raise InvalidFilterError("Invalid filter expression")


def create_rule_from_tuple(rule_tuple: FilterRuleTuple) -> FilterRule | None:
    if len(rule_tuple) < 2:
        raise InvalidFilterError("Rule must have at least 2 elements")

    field = rule_tuple[0]
    operator = cast(FilterOperator, rule_tuple[1])

    if operator not in get_args(FilterOperator):
        raise InvalidFilterError(f"Operator '{operator}' is not supported")

    value = rule_tuple[2] if len(rule_tuple) > 2 else None

    return R(field, operator, value)


def create_condition_from_tuple(
    condition_tuple: FilterConditionTuple,
) -> FilterCondition | None:
    if len(condition_tuple) != 2:
        raise InvalidFilterError("Condition must have 2 elements")

    condition_type = cast(FilterConditionType, condition_tuple[0])
    rules_data = condition_tuple[1]

    if condition_type not in get_args(FilterConditionType):
        raise InvalidFilterError(f"Condition type '{condition_type}' is not supported")

    rules = []

    for rule_data in rules_data:
        if is_rule(rule_data):
            rule = create_rule_from_tuple(cast(FilterRuleTuple, rule_data))

            if rule:
                rules.append(rule)
        elif is_condition(rule_data):
            nested_condition = create_condition_from_tuple(
                cast(FilterConditionTuple, rule_data)
            )

            if nested_condition:
                rules.append(nested_condition)

    if condition_type == "&":
        return And(*rules) if rules else None
    else:
        return Or(*rules) if rules else None


__all__ = [
    "parse_filter_input",
    "parse_filter_input_str",
    "parse_filter_input_array_to_tuple",
    "parse_filter_input_tuple",
    "create_rule_from_tuple",
    "create_condition_from_tuple",
]
