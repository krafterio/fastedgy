# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

# Operators
from fastedgy.orm.filter.operators import (
    FilterOperator,
    FilterConditionType,
    FILTER_OPERATORS_SQL,
    FILTER_DICT_OPERATORS_SQL,
    FILTER_OPERATORS_SQL_UNPACK,
    FILTER_OPERATORS_FIELD_MAP,
    FILTER_FIELD_TYPE_NAME_MAP,
    get_filter_operators,
)

# Types
from fastedgy.orm.filter.types import (
    InvalidFilterError,
    FilterRule,
    FilterCondition,
    R,
    And,
    Or,
    FilterRules,
    Filter,
    FilterRuleTuple,
    FilterRulesTuple,
    FilterConditionTuple,
    FilterTuple,
)

# Utils
from fastedgy.orm.filter.utils import (
    is_rule,
    is_condition,
    merge_filters,
    add_prefix_on_fields,
)

# Parser
from fastedgy.orm.filter.parser import (
    parse_filter_input,
    parse_filter_input_str,
    parse_filter_input_array_to_tuple,
    parse_filter_input_tuple,
    create_rule_from_tuple,
    create_condition_from_tuple,
)

# Validator
from fastedgy.orm.filter.validator import (
    validate_filters,
    validate_filter_field,
    validate_filter_operator,
)

# Builder
from fastedgy.orm.filter.builder import (
    build_filter_expression,
    filter_query,
)


__all__ = [
    # Operators
    "FilterOperator",
    "FilterConditionType",
    "FILTER_OPERATORS_SQL",
    "FILTER_DICT_OPERATORS_SQL",
    "FILTER_OPERATORS_SQL_UNPACK",
    "FILTER_OPERATORS_FIELD_MAP",
    "FILTER_FIELD_TYPE_NAME_MAP",
    "get_filter_operators",
    # Types
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
    # Utils
    "is_rule",
    "is_condition",
    "merge_filters",
    "add_prefix_on_fields",
    # Parser
    "parse_filter_input",
    "parse_filter_input_str",
    "parse_filter_input_array_to_tuple",
    "parse_filter_input_tuple",
    "create_rule_from_tuple",
    "create_condition_from_tuple",
    # Validator
    "validate_filters",
    "validate_filter_field",
    "validate_filter_operator",
    # Builder
    "build_filter_expression",
    "filter_query",
]
