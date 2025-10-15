# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, get_args
from dataclasses import dataclass

from fastedgy.orm.filter.operators import FilterOperator, FilterConditionType


class InvalidFilterError(Exception): ...


@dataclass(frozen=True)
class FilterRule:
    field: str
    operator: FilterOperator
    value: Any | None = None

    def __post_init__(self):
        if self.operator not in get_args(FilterOperator):
            raise ValueError(f"Operator '{self.operator}' is not supported")


@dataclass(frozen=True)
class FilterCondition:
    condition: FilterConditionType
    rules: list["FilterRule | FilterCondition"]

    def __post_init__(self):
        if self.condition not in get_args(FilterConditionType):
            raise ValueError(f"Condition '{self.condition}' is not supported")


@dataclass(frozen=True)
class R(FilterRule): ...


class And(FilterCondition):
    def __init__(self, *rules: FilterRule | FilterCondition):
        super().__init__(condition="&", rules=list(rules))


class Or(FilterCondition):
    def __init__(self, *rules: FilterRule | FilterCondition):
        super().__init__(condition="|", rules=list(rules))


FilterRules = list[FilterRule | FilterCondition]
Filter = FilterRule | FilterCondition | FilterRules


FilterRuleTuple = tuple[str, FilterOperator, Any | None]
FilterRulesTuple = list[FilterRuleTuple | type("FilterConditionTuple")]
FilterConditionTuple = tuple[FilterConditionType, FilterRulesTuple]
FilterTuple = FilterRuleTuple | FilterConditionTuple | FilterRulesTuple


__all__ = [
    "InvalidFilterError",
    "FilterRule",
    "FilterCondition",
    "R",
    "And",
    "Or",
    "FilterRules",
    "Filter",
    "FilterRuleTuple",
    "FilterRulesTuple",
    "FilterConditionTuple",
    "FilterTuple",
]
