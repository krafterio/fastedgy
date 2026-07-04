# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.orm import Model, BaseModelType
from fastedgy.orm.fields import BaseFieldType
from fastedgy.orm.query import QuerySet
from fastedgy.orm.utils import extract_field_names, find_primary_key_field


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

    model_cls = _real_model_cls(model_cls)

    # Convert string to list
    if isinstance(fields_expr, str):
        parts = [part.strip() for part in fields_expr.split(",")]
    else:
        parts = fields_expr

    result: dict[str, Any] = {"id": True}

    if "+" in parts:
        for field_name, field in model_cls.meta.fields.items():
            _add_field_selector(result, field)

        # Pydantic @computed_field values are not part of meta.fields (which only
        # holds ORM columns/relations), so the "+" wildcard would otherwise drop
        # them. Include them here so computed properties are emitted like columns.
        for computed_name in getattr(model_cls, "model_computed_fields", {}):
            result[computed_name] = True

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
                extra_fields = context.get_map_workspace_extra_fields(generate_metadata_name(model_cls))

                if extra_field_name in extra_fields:
                    result[field_path[0]] = True
            elif field_path[0] in getattr(current_model, "model_computed_fields", {}):
                # Explicitly requested @computed_field (not an ORM column, so
                # absent from meta.fields). Mirror the "+" wildcard behaviour.
                result[field_path[0]] = True
            else:
                _add_field_selector(current, current_model.meta.fields.get(field_path[0]))
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
                    elif field_name in current and isinstance(current[field_name], dict):
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
                is_computed = last_field in getattr(current_model, "model_computed_fields", {})

                if field or is_computed:
                    if isinstance(current, list):
                        current[0][last_field] = True
                    else:
                        current[last_field] = True

    return result


def clean_field_names_from_input(model_cls: type[BaseModelType], fields: str | list[str] | None) -> list[str]:
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
    query: QuerySet, fields_expr: str | list[str] | None, prune_columns: bool = True
) -> QuerySet:
    """
    Optimize query by preloading requested relationships and pruning unselected columns.

    Args:
        query: The QuerySet to optimize
        fields_expr: Field paths expression
        prune_columns: Restrict the SELECT to the requested columns via defer()

    Returns:
        Optimized QuerySet with select_related() and defer() applied
    """
    if not fields_expr:
        return query

    map_fields = parse_field_selector_input(query.model_class, fields_expr)

    if not map_fields:
        return query

    return apply_field_map_optimizations(query, map_fields, prune_columns=prune_columns)


def apply_field_map_optimizations(query: QuerySet, map_fields: dict[str, Any], prune_columns: bool = True) -> QuerySet:
    """
    Apply select_related() and defer() to a query from a parsed fields map.

    Relation paths are collected recursively for to-one relations. To-many relations
    are excluded: they are loaded by dedicated sub-queries at serialization time,
    which are themselves optimized with their sub-map.

    Column pruning uses defer() rather than only() because the defer flag is the
    only one propagated by Edgy to the nested instances built from joined rows:
    they must be proxy models (no pydantic validation on partial data, lazy load
    allowed on missing attributes).

    Relation querysets (m2m through models) embed their target at the
    embed_parent path: the map is then applied at that prefix.
    """
    model_cls = query.model_class
    base_prefix = ""
    embed_parent = getattr(query, "embed_parent", None)

    if embed_parent and embed_parent[0]:
        embedded_model = _resolve_relation_path(model_cls, embed_parent[0])

        if embedded_model is None:
            return query

        model_cls = embedded_model
        base_prefix = embed_parent[0]

    select_paths: set[str] = set()
    levels: dict[str, tuple[type[BaseModelType], set[str] | None]] = {}

    _collect_query_optimizations(model_cls, map_fields, base_prefix, select_paths, levels)

    for path in sorted(select_paths):
        try:
            query = query.select_related(path)
        except Exception:
            pass

    if prune_columns:
        defer_paths = _build_defer_paths(select_paths, levels)

        if defer_paths:
            from fastedgy.orm.deferred_batch import enable_deferred_batch_loading

            try:
                query = query.defer(*sorted(defer_paths))
                query = enable_deferred_batch_loading(query)
            except Exception:
                pass

    return query


def get_computed_field_deps(model_cls: type, field_name: str) -> tuple[str, ...] | None:
    info = getattr(_real_model_cls(model_cls), "model_computed_fields", {}).get(field_name)

    if info is None:
        return None

    prop = getattr(info, "wrapped_property", None)
    fget = getattr(prop, "fget", None) or prop

    return getattr(fget, "__computed_field_deps__", None)


def _collect_query_optimizations(
    model_cls: type[BaseModelType],
    fields_map: dict[str, Any],
    prefix: str,
    select_paths: set[str],
    levels: dict[str, tuple[type[BaseModelType], set[str] | None]],
) -> None:
    _keep_field(levels, model_cls, prefix, find_primary_key_field(model_cls))

    for field_name, field_value in fields_map.items():
        if isinstance(field_value, list):
            continue

        if isinstance(field_value, dict):
            field = model_cls.meta.fields.get(field_name)
            target = getattr(field, "target", None)

            if field is None or target is None or getattr(field, "is_m2m", False):
                continue

            _keep_field(levels, model_cls, prefix, field_name)
            target_pk = find_primary_key_field(target)

            if target_pk and set(field_value.keys()) <= {target_pk}:
                continue

            path = f"{prefix}__{field_name}" if prefix else field_name
            select_paths.add(path)
            _collect_query_optimizations(target, field_value, path, select_paths, levels)
            continue

        if field_name in getattr(model_cls, "model_computed_fields", {}):
            deps = get_computed_field_deps(model_cls, field_name)

            if deps is None:
                _opt_out_column_pruning(levels, model_cls, prefix)
            else:
                for dep in deps:
                    _merge_computed_dep(model_cls, dep, prefix, select_paths, levels)
            continue

        if field_name.startswith("extra_") and "extra" in model_cls.meta.fields:
            _keep_field(levels, model_cls, prefix, "extra")
            continue

        if field_name in model_cls.meta.fields:
            _keep_field(levels, model_cls, prefix, field_name)
        else:
            _opt_out_column_pruning(levels, model_cls, prefix)


def _merge_computed_dep(
    model_cls: type[BaseModelType],
    dep: str,
    prefix: str,
    select_paths: set[str],
    levels: dict[str, tuple[type[BaseModelType], set[str] | None]],
    depth: int = 0,
) -> None:
    if depth > 10:
        _opt_out_column_pruning(levels, model_cls, prefix)
        return

    parts = [part for part in dep.split(".") if part]
    current_model = model_cls
    current_prefix = prefix

    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1

        if part in getattr(current_model, "model_computed_fields", {}):
            sub_deps = get_computed_field_deps(current_model, part)

            if sub_deps is None:
                _opt_out_column_pruning(levels, current_model, current_prefix)
            else:
                for sub_dep in sub_deps:
                    _merge_computed_dep(current_model, sub_dep, current_prefix, select_paths, levels, depth + 1)
            return

        if part.startswith("extra_") and "extra" in current_model.meta.fields:
            _keep_field(levels, current_model, current_prefix, "extra")
            return

        field = current_model.meta.fields.get(part)

        if field is None:
            _opt_out_column_pruning(levels, current_model, current_prefix)
            return

        if is_last:
            _keep_field(levels, current_model, current_prefix, part)
            return

        target = getattr(field, "target", None)

        if target is None or getattr(field, "is_m2m", False):
            _opt_out_column_pruning(levels, current_model, current_prefix)
            return

        _keep_field(levels, current_model, current_prefix, part)
        current_prefix = f"{current_prefix}__{part}" if current_prefix else part
        select_paths.add(current_prefix)
        current_model = target
        _keep_field(levels, current_model, current_prefix, find_primary_key_field(current_model))


def _keep_field(
    levels: dict[str, tuple[type[BaseModelType], set[str] | None]],
    model_cls: type[BaseModelType],
    prefix: str,
    field_name: str | None,
) -> None:
    level = levels.get(prefix)

    if level is None:
        level = (model_cls, set())
        levels[prefix] = level

    kept_fields = level[1]

    if field_name is not None and kept_fields is not None:
        kept_fields.add(field_name)


def _opt_out_column_pruning(
    levels: dict[str, tuple[type[BaseModelType], set[str] | None]],
    model_cls: type[BaseModelType],
    prefix: str,
) -> None:
    levels[prefix] = (model_cls, None)


def _build_defer_paths(
    select_paths: set[str],
    levels: dict[str, tuple[type[BaseModelType], set[str] | None]],
) -> set[str]:
    defer_paths: set[str] = set()

    for prefix, (model_cls, kept_fields) in levels.items():
        if kept_fields is None:
            continue

        columns_map = getattr(model_cls.meta, "field_to_column_names", {})

        for field_name in model_cls.meta.fields:
            if field_name in kept_fields:
                continue

            if not columns_map.get(field_name):
                continue

            field_path = f"{prefix}__{field_name}" if prefix else field_name

            if field_path in select_paths:
                continue

            defer_paths.add(field_path)

    return defer_paths


async def filter_selected_fields(item: Model, fields_expr: str | list[str] | None) -> dict:
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
    map_fields = parse_field_selector_input(type(item), fields_expr)

    if map_fields is None:
        return item.model_dump()

    filtered_item: dict = {}
    await filter_fields(_dump_selected(item, map_fields), item, map_fields, filtered_item)

    return filtered_item


async def filter_fields(data: dict, data_obj: Model | None, fields: dict, target: dict) -> None:
    """
    Recursively filter fields from data based on fields dict.

    Args:
        data: Source data dict
        data_obj: Source model instance (for lazy loading)
        fields: Fields selector dict
        target: Target dict to populate
    """
    for field_name, field_value in fields.items():
        if isinstance(field_value, dict):
            if data_obj is not None:
                nested_obj = _get_loaded_relation(data_obj, field_name)

                if nested_obj is not None:
                    target[field_name] = {}
                    await filter_fields(
                        _dump_selected(nested_obj, field_value), nested_obj, field_value, target[field_name]
                    )
                else:
                    target[field_name] = None
        elif isinstance(field_value, list):
            if data_obj and hasattr(data_obj, field_name):
                nested_obj = getattr(data_obj, field_name, None)

                if nested_obj is not None:
                    target[field_name] = []
                    queryset = nested_obj.limit(1000).all()
                    queryset = apply_field_map_optimizations(queryset, field_value[0])
                    queryset = _inject_relation_default_order(queryset, data_obj, field_name, nested_obj)

                    items = [item async for item in queryset]

                    for obj_item in items:
                        item_data = _dump_selected(obj_item, field_value[0])
                        target[field_name].append({})
                        await filter_fields(item_data, obj_item, field_value[0], target[field_name][-1])
                else:
                    target[field_name] = []
        else:
            if field_name in data:
                target[field_name] = data[field_name]
            elif data_obj and hasattr(data_obj, field_name):
                target[field_name] = getattr(data_obj, field_name)


def _inject_relation_default_order(queryset: Any, data_obj: Model, field_name: str, nested_obj: Any) -> Any:
    from fastedgy.orm.order_by import inject_order_by, parse_order_by

    field = _real_model_cls(type(data_obj)).meta.fields.get(field_name)
    target_model = None

    if field is not None:
        target_model = getattr(field, "target", None) or getattr(field, "related_from", None)

    if target_model is None or not hasattr(target_model, "Meta"):
        if hasattr(nested_obj, "Meta"):
            order_by_input = getattr(nested_obj.Meta, "default_order_by", None)

            if order_by_input:
                return inject_order_by(queryset, order_by_input)

        return queryset

    order_by_input = getattr(target_model.Meta, "default_order_by", None)

    if not order_by_input:
        return queryset

    return inject_order_by(queryset, parse_order_by(target_model, order_by_input))


def _real_model_cls(model_cls: type[BaseModelType]) -> type[BaseModelType]:
    if getattr(model_cls, "__is_proxy_model__", False):
        return getattr(model_cls, "__parent__", None) or model_cls

    return model_cls


def _resolve_relation_path(model_cls: type[BaseModelType], path: str) -> type[BaseModelType] | None:
    current_model = model_cls

    for part in path.split("__"):
        field = current_model.meta.fields.get(part)
        target = getattr(field, "target", None)

        if target is None:
            return None

        current_model = target

    return current_model


def _dump_selected(item: Model, fields_map: dict[str, Any]) -> dict:
    model_cls = _real_model_cls(type(item))
    computed_fields = getattr(model_cls, "model_computed_fields", {})
    include: set[str] = set()

    for field_name, field_value in fields_map.items():
        if field_value is not True:
            continue

        if field_name.startswith("extra_") and "extra" in model_cls.meta.fields:
            include.add("extra")
        elif field_name in model_cls.meta.fields or field_name in computed_fields:
            include.add(field_name)

    pk_name = find_primary_key_field(model_cls)

    if pk_name:
        include.add(pk_name)

    return item.model_dump(include=include)


def _get_loaded_relation(data_obj: Model, field_name: str) -> Any:
    from edgy.core.db.context_vars import MODEL_GETATTR_BEHAVIOR

    token = MODEL_GETATTR_BEHAVIOR.set("passdown")

    try:
        return getattr(data_obj, field_name)
    except AttributeError:
        return None
    finally:
        MODEL_GETATTR_BEHAVIOR.reset(token)


def _add_field_selector(fields: dict[str, Any], field: BaseFieldType, force: bool = False):
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
    "apply_field_map_optimizations",
    "get_computed_field_deps",
    "filter_selected_fields",
    "filter_fields",
]
