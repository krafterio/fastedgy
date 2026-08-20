# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

# Operators
# Builder
from fastedgy.orm.filter.builder import (
    build_filter_expression,
    filter_query,
)

# Global filters
from fastedgy.orm.filter.global_filters import (
    GlobalFilter,
    GlobalFilterApply,
    GlobalFilterGetter,
    GlobalFilterRegistry,
    apply_global_filters,
    global_filter,
)
from fastedgy.orm.filter.operators import (
    FILTER_DICT_OPERATORS_SQL,
    FILTER_FIELD_TYPE_NAME_MAP,
    FILTER_OPERATORS_FIELD_MAP,
    FILTER_OPERATORS_SQL,
    FILTER_OPERATORS_SQL_UNPACK,
    FilterConditionType,
    FilterOperator,
    get_filter_operators,
)

# Parser
from fastedgy.orm.filter.parser import (
    create_condition_from_tuple,
    create_rule_from_tuple,
    parse_filter_input,
    parse_filter_input_array_to_tuple,
    parse_filter_input_str,
    parse_filter_input_tuple,
)

# Types
from fastedgy.orm.filter.types import (
    And,
    Filter,
    FilterCondition,
    FilterConditionTuple,
    FilterRule,
    FilterRules,
    FilterRulesTuple,
    FilterRuleTuple,
    FilterTuple,
    InvalidFilterError,
    Or,
    R,
)

# Utils
from fastedgy.orm.filter.utils import (
    add_prefix_on_fields,
    is_condition,
    is_rule,
    merge_filters,
)

# Validator
from fastedgy.orm.filter.validator import (
    validate_filter_field,
    validate_filter_operator,
    validate_filters,
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
    # Global filters
    "GlobalFilter",
    "GlobalFilterRegistry",
    "GlobalFilterGetter",
    "GlobalFilterApply",
    "global_filter",
    "apply_global_filters",
]
