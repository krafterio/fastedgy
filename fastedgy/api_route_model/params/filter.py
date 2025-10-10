# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, get_args, cast, Callable, Type
from dataclasses import dataclass
import json

from fastapi.params import Query, Header

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
from fastedgy.orm.filter import (
    get_filter_operators,
    FilterOperator,
    FilterConditionType,
    FILTER_OPERATORS_SQL,
    FILTER_DICT_OPERATORS_SQL,
    FILTER_OPERATORS_SQL_UNPACK,
)
from fastedgy.orm.query import QuerySet
from fastedgy.orm.utils import find_primary_key_field


class InvalidFilterError(Exception): ...


class FilterQuery(Query):
    def __init__(self):
        super().__init__(
            default=None,
            title="Filter",
            description="Filter the list of items with the filter expression build with rules and conditions",
        )


class FilterHeader(Header):
    def __init__(self):
        super().__init__(
            default=None,
            title="Filter",
            description="Filter the list of items with the filter expression build with rules and conditions",
            alias="X-Filter",
        )


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
    rules: list[FilterRule | FilterConditionType]

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


def is_rule(item: Any) -> bool:
    if isinstance(item, FilterRule):
        return True

    return (
        (isinstance(item, tuple) or isinstance(item, list))
        and 2 <= len(item) <= 3
        and isinstance(item[0], str)
        and isinstance(item[1], str)
    )


def is_condition(item: Any) -> bool:
    if isinstance(item, FilterCondition):
        return True

    return (
        (isinstance(item, tuple) or isinstance(item, list))
        and len(item) == 2
        and isinstance(item[0], str)
        and isinstance(item[1], list)
    )


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
        data = json.loads(filters)
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


def merge_filters(*filters: Filter) -> FilterCondition | None:
    parsed_filters = []

    for filter_item in filters:
        if filter_item is None:
            continue

        if isinstance(filter_item, str):
            parsed = parse_filter_input_str(filter_item)

            if parsed:
                parsed_filters.append(parsed)
        elif isinstance(filter_item, (tuple, list)):
            parsed = parse_filter_input_tuple(filter_item)  # type: ignore

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


def add_prefix_on_fields(
    field_prefix: str, filters: list | FilterTuple | None
) -> FilterTuple | None:
    if not filters:
        return None

    if isinstance(filters, list):
        filters = parse_filter_input_array_to_tuple(filters)

    if is_rule(filters):
        field, operator, value = filters

        return f"{field_prefix}.{field}", operator, value

    elif is_condition(filters):
        condition, rules = filters
        new_rules = []

        for rule in rules:
            new_rules.append(add_prefix_on_fields(field_prefix, rule))

        return condition, new_rules

    elif isinstance(filters, list):
        return [add_prefix_on_fields(field_prefix, item) for item in filters]

    return filters


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
    "InvalidFilterError",
    "FilterQuery",
    "FilterHeader",
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
    "is_rule",
    "is_condition",
    "parse_filter_input",
    "parse_filter_input_str",
    "parse_filter_input_array_to_tuple",
    "parse_filter_input_tuple",
    "create_rule_from_tuple",
    "create_condition_from_tuple",
    "merge_filters",
    "add_prefix_on_fields",
    "validate_filters",
    "validate_filter_field",
    "validate_filter_operator",
    "build_filter_expression",
    "filter_query",
]
