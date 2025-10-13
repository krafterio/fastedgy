# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastapi.params import Query, Header

from fastedgy.orm import Model, BaseModelType
from fastedgy.orm.fields import BaseFieldType
from fastedgy.orm.query import QuerySet
from fastedgy.orm.utils import extract_field_names
from fastedgy.api_route_model.params.order_by import inject_order_by


class FieldSelectorQuery(Query):
    def __init__(self):
        super().__init__(
            default=None,
            title="Fields Selector",
            description="Select which fields to include in the response and use dot notation to select nested fields (ex. 'name,company.name')",
        )


class FieldSelectorHeader(Header):
    def __init__(self):
        super().__init__(
            default=None,
            title="Fields Selector",
            description="Select which fields to include in the response and use dot notation to select nested fields (ex. 'name,company.name')",
            alias="X-Fields",
        )


def parse_field_selector_input(
    model_cls: type[BaseModelType], fields_expr: str | None
) -> dict[str, Any] | None:
    """
    Parse a fields expression into a structured dictionary.
    """
    if not fields_expr or not fields_expr.strip():
        return None

    parts = [part.strip() for part in fields_expr.split(",")]
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
                else:
                    break

            if current and current_model:
                field = current_model.meta.fields.get(last_field)

                if field:
                    if isinstance(current, list):
                        current[0][last_field] = True
                    else:
                        current[last_field] = True

    return result


def clean_field_names_from_input(
    model_cls: type[BaseModelType], fields_expr: str | None
) -> list[str]:
    fields = [part.strip() for part in fields_expr.split(",")] if fields_expr else []
    fields_map = parse_field_selector_input(model_cls, fields_expr)
    valid_fields = extract_field_names(fields_map) if fields_map else []

    return [field for field in fields if field in valid_fields]


async def filter_fields(
    data: dict, data_obj: Model, fields_map: dict, target: dict
) -> None:
    """Filter data recursively based on the field selector."""
    for field_name, field_value in fields_map.items():
        # Si le champ est une structure imbriquée
        if isinstance(field_value, dict):
            if field_name in data and data[field_name] is not None:
                if field_name not in target:
                    target[field_name] = {}

                nested_data = data[field_name]
                nested_obj = getattr(data_obj, field_name, None) if data_obj else None

                if isinstance(nested_data, dict):
                    await filter_fields(
                        nested_data, nested_obj, field_value, target[field_name]
                    )

                    if not target[field_name]:
                        target[field_name] = None

                elif isinstance(nested_data, list):
                    target[field_name] = []

                    for i, item in enumerate(nested_data):
                        if isinstance(item, dict):
                            target[field_name].append({})
                            nested_item_obj = (
                                nested_obj[i]
                                if nested_obj and i < len(nested_obj)
                                else None
                            )
                            await filter_fields(
                                item,
                                nested_item_obj,
                                field_value,
                                target[field_name][i],
                            )
                        else:
                            target[field_name].append(item)

            elif data_obj and hasattr(data_obj, field_name):
                nested_obj = getattr(data_obj, field_name, None)
                if nested_obj is not None:
                    if isinstance(nested_obj, Model):
                        nested_data = nested_obj.model_dump()

                        if isinstance(nested_data, dict):
                            target[field_name] = {}
                            await filter_fields(
                                nested_data, nested_obj, field_value, target[field_name]
                            )

                            if not target[field_name]:
                                target[field_name] = None

                        elif isinstance(nested_obj, list):
                            target[field_name] = []

                            for i, obj_item in enumerate(nested_obj):
                                if hasattr(obj_item, "model_dump"):
                                    item_data = obj_item.model_dump()
                                    target[field_name].append({})
                                    filter_fields(
                                        item_data,
                                        obj_item,
                                        field_value,
                                        target[field_name][i],
                                    )
                                else:
                                    target[field_name].append(obj_item)
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


async def filter_selected_fields(item: Model, fields_expr: str | None) -> dict:
    """
    Filters the fields of a model object based on the field selector.

    Note: This function does not optimize the query. To optimize queries,
    use the optimize_query_filter_fields() function directly on the query
    before executing first(), get(), or all().
    """
    map_fields = parse_field_selector_input(item.meta.model, fields_expr)
    item_dump = item.model_dump()

    if map_fields is not None:
        filtered_item = {}
        await filter_fields(item_dump, item, map_fields, filtered_item)
        item_dump = filtered_item

    return item_dump


def optimize_query_filter_fields(query: QuerySet, fields_expr: str | None) -> QuerySet:
    """
    Optimizes the query by preloading the requested relationships into the field selector.
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


def _add_field_selector(
    fields: dict[str, Any], field: BaseFieldType, force: bool = False
):
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
    "FieldSelectorQuery",
    "FieldSelectorHeader",
    "parse_field_selector_input",
    "clean_field_names_from_input",
    "filter_fields",
    "filter_selected_fields",
    "optimize_query_filter_fields",
]
