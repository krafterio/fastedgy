# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.orm import Model, BaseModelType
from fastedgy.orm.fields import BaseFieldType
from fastedgy.orm.query import QuerySet
from fastedgy.orm.utils import extract_field_names


def parse_field_selector_input(
    model_cls: type[BaseModelType], fields_expr: str | list[str] | None
) -> dict[str, Any] | None:
    """
    Parse a fields expression into a structured dictionary.

    Args:
        model_cls: The model class to parse fields for
        fields_expr: Comma-separated string or list of field paths
                    (e.g. "name,company.name" or ["name", "company.name"])

    Returns:
        Structured dict representing fields to include, or None if no fields specified
        Example: {"id": True, "name": True, "company": {"id": True, "name": True}}
    """
    if not fields_expr or (isinstance(fields_expr, str) and not fields_expr.strip()):
        return None

    # Convert string to list
    if isinstance(fields_expr, str):
        parts = [part.strip() for part in fields_expr.split(",")]
    else:
        parts = fields_expr

    result = {"id": True}

    if "+" in parts:
        for field_name, field in model_cls.meta.fields.items():
            _add_field_selector(result, field)

    for part in parts:
        if part == "+":
            continue

        # Handle nested fields (e.g., "owner.name")
        field_path = part.split(".")
        current = result
        current_model = model_cls

        if len(field_path) == 1:
            if field_path[0].startswith("extra_"):
                from fastedgy import context
                from fastedgy.metadata_model.generator import generate_metadata_name

                extra_field_name = field_path[0][6:]
                extra_fields = context.get_map_workspace_extra_fields(
                    generate_metadata_name(model_cls)
                )

                if extra_field_name in extra_fields:
                    result[field_path[0]] = True
            else:
                _add_field_selector(
                    current, current_model.meta.fields.get(field_path[0])
                )
        else:
            parent_path = field_path[:-1]
            last_field = field_path[-1]

            for i, field_name in enumerate(parent_path):
                if current and current_model:
                    field = current_model.meta.fields.get(field_name)

                    if field_name not in current:
                        _add_field_selector(current, field, True)

                    if field_name in current and isinstance(current[field_name], list):
                        current = current[field_name][0]
                    elif field_name in current and isinstance(
                        current[field_name], dict
                    ):
                        current = current[field_name]
                    else:
                        current[field_name] = {"id": True}
                        current = current[field_name]

                    if field and hasattr(field, "target"):
                        current_model = field.target
                    elif field and hasattr(field, "related_from"):
                        current_model = field.related_from
                    else:
                        current_model = None

            if current and current_model:
                field = current_model.meta.fields.get(last_field)

                if field:
                    if isinstance(current, list):
                        current[0][last_field] = True
                    else:
                        current[last_field] = True

    return result


def clean_field_names_from_input(
    model_cls: type[BaseModelType], fields: str | list[str] | None
) -> list[str]:
    """
    Clean and validate field paths, returning a flat list.

    Args:
        model_cls: The model class to validate fields for
        fields: Comma-separated string or list of field paths

    Returns:
        List of valid field paths (e.g. ["name", "company.name", "tags.name"])
    """
    if not fields:
        return []

    # Convert to list if string
    if isinstance(fields, str):
        parts = [part.strip() for part in fields.split(",") if part.strip()]
    else:
        parts = fields

    parsed = parse_field_selector_input(model_cls, parts)

    if not parsed:
        return []

    return extract_field_names(parsed)


def optimize_query_filter_fields(
    query: QuerySet, fields_expr: str | list[str] | None
) -> QuerySet:
    """
    Optimize query by preloading requested relationships.

    Args:
        query: The QuerySet to optimize
        fields_expr: Field paths expression

    Returns:
        Optimized QuerySet with select_related() applied
    """
    if not fields_expr:
        return query

    model_cls = query.model_class
    map_fields = parse_field_selector_input(model_cls, fields_expr)

    if not map_fields:
        return query

    direct_relations = []
    has_list_relations = False

    def collect_relations(fields_map: dict) -> None:
        nonlocal has_list_relations
        for field_name, field_value in fields_map.items():
            if isinstance(field_value, dict) or isinstance(field_value, list):
                field = model_cls.meta.fields.get(field_name)

                if field:
                    if hasattr(field, "target"):
                        direct_relations.append(field_name)
                        if getattr(field, "is_m2m", False):
                            has_list_relations = True
                    elif hasattr(field, "related_from"):
                        direct_relations.append(field_name)
                        has_list_relations = True

    collect_relations(map_fields)

    for relation in direct_relations:
        try:
            query = query.select_related(relation)
        except Exception:
            pass

    if has_list_relations and query.distinct_on is None:
        from fastedgy.orm.utils import find_primary_key_field

        primary_key = find_primary_key_field(model_cls)
        if primary_key:
            query = query.distinct(primary_key)

    return query


async def filter_selected_fields(
    item: Model, fields_expr: str | list[str] | None
) -> dict:
    """
    Filter fields of a model instance based on field paths.

    Args:
        item: Model instance to filter
        fields_expr: Field paths expression

    Returns:
        Filtered dict with only requested fields

    Note: This function does not optimize the query. To optimize queries,
    use optimize_query_filter_fields() function directly on the query
    before executing first(), get(), or all().
    """
    map_fields = parse_field_selector_input(item.meta.model, fields_expr)
    item_dump = item.model_dump()

    if map_fields is not None:
        filtered_item = {}
        await filter_fields(item_dump, item, map_fields, filtered_item)
        item_dump = filtered_item

    return item_dump


async def filter_fields(
    data: dict, data_obj: Model | None, fields: dict, target: dict
) -> None:
    """
    Recursively filter fields from data based on fields dict.

    Args:
        data: Source data dict
        data_obj: Source model instance (for lazy loading)
        fields: Fields selector dict
        target: Target dict to populate
    """
    from fastedgy.api_route_model.params.order_by import inject_order_by

    for field_name, field_value in fields.items():
        if isinstance(field_value, dict):
            if data_obj and hasattr(data_obj, field_name):
                nested_obj = getattr(data_obj, field_name, None)

                if nested_obj is not None:
                    nested_data = nested_obj.model_dump()
                    target[field_name] = {}
                    await filter_fields(
                        nested_data, nested_obj, field_value, target[field_name]
                    )
                else:
                    target[field_name] = None
        elif isinstance(field_value, list):
            if data_obj and hasattr(data_obj, field_name):
                nested_obj = getattr(data_obj, field_name, None)

                if nested_obj is not None:
                    target[field_name] = []
                    queryset = nested_obj.limit(1000).all()

                    if hasattr(nested_obj, "Meta"):
                        order_by_input = getattr(
                            nested_obj.Meta, "default_order_by", None
                        )

                        if order_by_input:
                            queryset = inject_order_by(queryset, order_by_input)

                    items = [item async for item in queryset]

                    for obj_item in items:
                        item_data = obj_item.model_dump()
                        target[field_name].append({})
                        await filter_fields(
                            item_data, obj_item, field_value[0], target[field_name][-1]
                        )
                else:
                    target[field_name] = []
        else:
            if field_name in data:
                target[field_name] = data[field_name]
            elif data_obj and hasattr(data_obj, field_name):
                target[field_name] = getattr(data_obj, field_name)


def _add_field_selector(
    fields: dict[str, Any], field: BaseFieldType, force: bool = False
):
    """
    Add a field to the selector dict with appropriate structure.

    Args:
        fields: Fields dict to add to
        field: Field to add
        force: Force adding even if excluded
    """
    if field and (not field.exclude or force):
        if getattr(field, "is_m2m", False):
            field_val = [{"id": True}]
        elif hasattr(field, "related_from"):
            field_val = [{"id": True}]
        elif hasattr(field, "target"):
            field_val = {"id": True}
        else:
            field_val = True

        fields.update({field.name: field_val})


__all__ = [
    "parse_field_selector_input",
    "clean_field_names_from_input",
    "optimize_query_filter_fields",
    "filter_selected_fields",
    "filter_fields",
]
