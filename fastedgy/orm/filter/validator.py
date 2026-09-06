# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import Model
from fastedgy.orm.filter.operators import ANY_OPERATORS, get_filter_operators
from fastedgy.orm.filter.types import (
    And,
    Filter,
    FilterCondition,
    FilterRule,
    InvalidFilterError,
    Or,
    R,
)


def validate_filters(
    model_cls: type[Model],
    filters: Filter | None,
    allow_excluded: bool = False,
) -> FilterRule | FilterCondition | None:
    if not filters:
        return None

    # Filter Rule
    if isinstance(filters, FilterRule):
        # A sub-filter rule names a relation, not a value: what it may read is
        # checked field by field on the model that relation reaches.
        if filters.operator in ANY_OPERATORS:
            if not validate_filter_operator(model_cls, filters.field, filters.operator):
                raise InvalidFilterError(f"Invalid operator {filters.operator} for field {filters.field}")

            return _validate_any_rule(model_cls, filters, allow_excluded=allow_excluded)

        if not validate_filter_field(model_cls, filters.field, allow_excluded=allow_excluded):
            raise InvalidFilterError(f"Invalid filter field: {filters.field}")

        if not validate_filter_operator(model_cls, filters.field, filters.operator):
            raise InvalidFilterError(f"Invalid operator {filters.operator} for field {filters.field}")

        return filters

    # Filter Condition
    if isinstance(filters, FilterCondition):
        validated_rules = []

        for rule in filters.rules:
            validated_rule = validate_filters(model_cls, rule, allow_excluded=allow_excluded)

            if validated_rule:
                validated_rules.append(validated_rule)

        if validated_rules:
            if filters.condition == "&":
                return And(*validated_rules)
            else:
                return Or(*validated_rules)

    raise InvalidFilterError("Invalid filter expression")


def _validate_any_rule(model_cls: type[Model], rule: FilterRule, allow_excluded: bool = False) -> FilterRule:
    """Validate the sub-filter an ``any`` rule carries against the model it reaches.

    The descent is what keeps the field checks honest: without it the sub-filter
    names columns nobody looked at, and a caller reads a field it may not see by
    bisecting on it.
    """
    from fastedgy.orm.filter.parser import parse_filter_input

    target_cls = resolve_relation_target(model_cls, rule.field)

    if target_cls is None:
        raise InvalidFilterError(f"Operator {rule.operator} needs a relation, {rule.field} is not one")

    sub_filters = rule.value

    if sub_filters and not isinstance(sub_filters, (FilterRule, FilterCondition)):
        sub_filters = parse_filter_input(sub_filters)

        if sub_filters is None:
            raise InvalidFilterError(f"Operator {rule.operator} on {rule.field} takes a filter as value")

    return R(rule.field, rule.operator, validate_filters(target_cls, sub_filters, allow_excluded=allow_excluded))


def resolve_relation_target(model_cls: type[Model], field_path: str) -> type[Model] | None:
    """The model a relation path reaches, or ``None`` when a hop is not a relation.

    A generic foreign key is not one: it points at any model, so it names no
    single one to resolve a sub-filter against. Its reverse side does.
    """
    current_cls = model_cls

    for part in field_path.split("."):
        field_info = current_cls.meta.fields.get(part)

        if field_info is None or getattr(field_info, "is_generic_foreign_key", False):
            return None

        if hasattr(field_info, "target"):
            current_cls = field_info.target
        elif hasattr(field_info, "related_from"):
            current_cls = field_info.related_from
        else:
            return None

    return current_cls


def validate_filter_field(model_cls: type[Model], field_path: str, allow_excluded: bool = False) -> bool:
    if not field_path:
        return False

    from fastedgy.orm.fields import resolve_generic_pair

    if resolve_generic_pair(model_cls, field_path) is not None:
        return True

    if field_path.startswith("extra_"):
        from fastedgy import context
        from fastedgy.metadata_model.generator import generate_metadata_name

        if "extra" not in model_cls.meta.fields:
            return False

        extra_field_name = field_path[6:]
        extra_fields = context.get_map_workspace_extra_fields(generate_metadata_name(model_cls))

        return extra_field_name in extra_fields

    parts = field_path.split(".")
    current_cls = model_cls

    for i, part in enumerate(parts):
        if part not in current_cls.meta.fields:
            return False

        field_info = current_cls.meta.fields.get(part)

        # Exclude ComputedField (not stored in DB, cannot be filtered)
        if hasattr(field_info, "getter"):
            return False

        if i < len(parts) - 1:
            if hasattr(field_info, "target"):
                current_cls = field_info.target
            elif hasattr(field_info, "related_from"):
                current_cls = field_info.related_from
            else:
                return False
        else:
            # Last field in path: check filterable
            is_excluded = getattr(field_info, "exclude", False)
            if is_excluded and not allow_excluded:
                if not getattr(field_info, "filterable", False):
                    return False
            elif not is_excluded and not getattr(field_info, "filterable", True):
                return False

    return True


def validate_filter_operator(model_cls: type[Model], field_path: str, operator: str) -> bool:
    if not field_path or not operator:
        return False

    from fastedgy.orm.fields import resolve_generic_pair

    generic_pair = resolve_generic_pair(model_cls, field_path)
    if generic_pair is not None:
        generic_field, side = generic_pair
        column_name = generic_field.model_column if side == "model" else generic_field.id_column
        return operator in get_filter_operators(model_cls.meta.fields[column_name])

    if field_path.startswith("extra_"):
        from fastedgy import context
        from fastedgy.metadata_model.generator import generate_metadata_name
        from fastedgy.models.workspace_extra_field import (
            EXTRA_FIELD_TYPE_OPTIONS,
            EXTRA_FIELDS_MAP,
        )

        if "extra" not in model_cls.meta.fields:
            return False

        extra_field_name = field_path[6:]
        extra_fields = context.get_map_workspace_extra_fields(generate_metadata_name(model_cls))

        if extra_field_name not in extra_fields:
            return False

        extra_field = extra_fields[extra_field_name]
        field_type_enum = extra_field.field_type

        if field_type_enum is None:
            return False

        field_type = EXTRA_FIELDS_MAP.get(field_type_enum)

        if not field_type:
            return False

        ft = field_type(**EXTRA_FIELD_TYPE_OPTIONS[field_type_enum])

        return operator in get_filter_operators(ft)

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
    "resolve_relation_target",
    "validate_filter_field",
    "validate_filter_operator",
    "validate_filters",
]
