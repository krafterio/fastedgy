# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Serialize a read straight from its rows, for what a read only reads.

The field selector already prunes the columns and joins the relations it needs;
what still costs is what comes after: a model instance per row *and per joined
relation*, validated by Pydantic, then walked again to take two or three values
out of it. On a page of fifty rows carrying three relations, that is around a
thousand objects for a few hundred values.

Nothing of that is needed when the answer is a partial read: nobody writes those
instances, nobody reads a relation of theirs afterwards. The values are already
in the row the query brought back, under the aliases Edgy gave the joins.

This is the exception, not the rule: it applies to a level made of columns
alone. A computed field, a to-many relation, a generic reference or a custom
field needs the instance, and the whole read goes back to the model path.
"""

from collections.abc import Iterable
from typing import Any, cast

from fastedgy.orm.order_by import OrderByList
from fastedgy.orm.query import QuerySet
from fastedgy.orm.utils import find_primary_key_field

__all__ = [
    "can_read_paths",
    "can_read_rows",
    "read_rows",
]

# What one row is served of a relation, the cap the per-row read applies too.
_READ_LIMIT = 1000


def _real_model_cls(model_cls: Any) -> Any:
    if getattr(model_cls, "__is_proxy_model__", False):
        return getattr(model_cls, "__parent__", None) or model_cls

    return model_cls


def _column_of(model_cls: Any, field_name: str) -> str | None:
    """The single column a field maps to, or None when it maps to none (a
    computed value) or to several (a composite key)."""
    columns = list(getattr(model_cls.meta, "field_to_column_names", {}).get(field_name, ()) or ())

    return columns[0] if len(columns) == 1 else None


def _to_many_of(model_cls: Any, field_name: str) -> tuple[Any, str, str | None, Any] | None:
    """What reads a to-many relation, read off the field rather than off an
    instance: the model holding the link, the key back to the owner, the key to
    the target when a link table stands between them, and the target."""
    from edgy.core.db.relationships.related_field import RelatedField

    field = _real_model_cls(model_cls).meta.fields.get(field_name)

    if getattr(field, "is_m2m", False):
        through = getattr(field, "through", None)
        target = getattr(field, "target", None)

        if through is None or target is None:
            return None

        return through, field.from_foreign_key, field.to_foreign_key, target

    if isinstance(field, RelatedField):
        return field.related_from, field.foreign_key_name, None, field.related_from

    return None


def can_read_rows(model_cls: Any, map_fields: dict[str, Any]) -> bool:
    """Whether every level of the selection is made of columns, to-one
    relations and to-many relations, the shapes rows answer on their own."""
    from fastedgy.orm.field_selector import is_computed_field

    model_cls = _real_model_cls(model_cls)

    for field_name, value in map_fields.items():
        if isinstance(value, list):
            plan = _to_many_of(model_cls, field_name)

            if plan is None or not can_read_rows(plan[3], value[0]):
                return False

            continue

        # A custom field lives in the JSON column its model carries, and the
        # selector keeps that column as soon as one is asked for.
        if field_name.startswith("extra_") and "extra" in model_cls.meta.fields:
            continue

        field = model_cls.meta.fields.get(field_name)

        if field is None or getattr(field, "is_generic_foreign_key", False):
            return False

        if isinstance(value, dict):
            target = getattr(field, "target", None)

            if target is None or getattr(field, "is_m2m", False):
                return False

            if not can_read_rows(target, value):
                return False

            continue

        if is_computed_field(model_cls, field_name):
            # It says what it reads, and the selector already keeps those
            # columns: the row carries everything the getter asks for.
            if not _deps_are_readable(model_cls, field_name):
                return False

            continue

        if _column_of(model_cls, field_name) is None:
            return False

        if getattr(field, "exclude", False) or getattr(field, "secret", False):
            return False

    return True


def can_read_paths(model_cls: Any, paths: Iterable[str]) -> bool:
    """Whether these dotted reads are answered by a row: a column of this level,
    or one reached through to-one relations."""
    from fastedgy.orm.field_selector import is_computed_field

    for path in paths:
        current = _real_model_cls(model_cls)
        parts = [part for part in path.split(".") if part]

        if not parts:
            return False

        for index, part in enumerate(parts):
            field = current.meta.fields.get(part)

            if field is None or part.startswith("extra_"):
                return False

            if index == len(parts) - 1:
                if is_computed_field(current, part) and not _deps_are_readable(current, part):
                    return False

                break

            target = getattr(field, "target", None)

            if target is None or getattr(field, "is_m2m", False):
                return False

            current = _real_model_cls(target)

    return True


def _deps_are_readable(model_cls: Any, field_name: str) -> bool:
    """Whether what a computed field says it reads can be read off the row.

    Undeclared, nothing here can know what its getter reaches for, and the read
    goes back to the models.
    """
    from fastedgy.orm.field_selector import get_computed_field_deps

    deps = get_computed_field_deps(_real_model_cls(model_cls), field_name)

    return deps is not None and can_read_paths(model_cls, deps)


def _allowed_tree(paths: Iterable[str]) -> dict[str, Any]:
    """What was named, level by level: ``{"workspace": {"id": {}}}``.

    An empty node is a name read for itself, and nothing below it.
    """
    tree: dict[str, Any] = {}

    for path in paths:
        name, _, rest = path.partition(".")
        node = tree.setdefault(name, {})

        if rest:
            node.update(_allowed_tree([rest]))

    return tree


class _RowValues:
    """What a computed field reads, answered from the row it was read with.

    It holds no state of its own: each name is a column of this level, or the
    relation joined into it, which answers the same way.
    """

    __slots__ = ("_allowed", "_mapping", "_model", "_path", "_tables")

    def __init__(
        self,
        mapping: Any,
        model_cls: Any,
        path: str,
        tables: dict[str, Any],
        allowed: dict[str, Any] | None = None,
    ) -> None:
        self._mapping = mapping
        self._model = _real_model_cls(model_cls)
        self._path = path
        self._tables = tables
        self._allowed = allowed

    def __getattr__(self, name: str) -> Any:
        from fastedgy.orm.field_selector import is_computed_field

        if self._allowed is not None and name not in self._allowed:
            raise AttributeError(
                f"{self._model.__name__}.{name} was not named by @view_transformer_reads: "
                "the read answered from its rows, and this one carries only what was named."
            )

        field = self._model.meta.fields.get(name)

        if field is None:
            raise AttributeError(name)

        if is_computed_field(self._model, name):
            return _computed_value(self._mapping, self._model, name, self._path, self._tables)

        target = getattr(field, "target", None)
        nested = f"{self._path}__{name}" if self._path else name

        if target is not None and nested in self._tables:
            if _is_null_row(self._mapping, target, nested, self._tables):
                return None

            allowed = self._allowed[name] if self._allowed is not None else None

            return _RowValues(self._mapping, target, nested, self._tables, allowed)

        return self._mapping.get(f"{_prefix_of(self._tables, self._path)}{_column_of(self._model, name)}")


def _computed_value(mapping: Any, model_cls: Any, field_name: str, path: str, tables: dict[str, Any]) -> Any:
    """The value a computed field takes, its getter reading the row."""
    model_cls = _real_model_cls(model_cls)
    reads = _RowValues(mapping, model_cls, path, tables)
    info = getattr(model_cls, "model_computed_fields", {}).get(field_name)

    if info is not None:
        prop = getattr(info, "wrapped_property", None)
        getter = getattr(prop, "fget", None) or prop

        return getter(reads) if getter else None

    field = model_cls.meta.fields.get(field_name)
    getter = getattr(field, "getter", None)

    if isinstance(getter, str):
        getter = getattr(model_cls, getter, None)

    return getter(field, reads) if getter else None


def _prefix_of(tables: dict[str, Any], path: str) -> str:
    """What Edgy named the columns of that level in the row."""
    table = tables.get(path) if path else None

    return f"{getattr(table[0], 'name', '')}_" if table else ""


def _is_null_row(mapping: Any, model_cls: Any, path: str, tables: dict[str, Any]) -> bool:
    """Whether a relation nothing points at: the left join answered with nulls."""
    model_cls = _real_model_cls(model_cls)
    primary_key = find_primary_key_field(model_cls)

    if not path or primary_key is None:
        return False

    return mapping.get(f"{_prefix_of(tables, path)}{_column_of(model_cls, primary_key)}") is None


def _read_level(
    mapping: Any,
    model_cls: Any,
    map_fields: dict[str, Any],
    path: str,
    tables: dict[str, Any],
) -> dict[str, Any] | None:
    from fastedgy.orm.field_selector import is_computed_field

    model_cls = _real_model_cls(model_cls)
    prefix = _prefix_of(tables, path)

    if _is_null_row(mapping, model_cls, path, tables):
        return None

    read: dict[str, Any] = {}

    for field_name, value in map_fields.items():
        if isinstance(value, list):
            # Read by itself, once for the whole page, and attached after.
            continue

        if isinstance(value, dict):
            target = model_cls.meta.fields[field_name].target
            nested = f"{path}__{field_name}" if path else field_name

            if nested in tables:
                read[field_name] = _read_level(mapping, target, value, nested, tables)

                continue

            # Asked for its key alone: the column of this level holds it, and
            # no join was needed to say so.
            target_key = find_primary_key_field(_real_model_cls(target))
            held = mapping.get(f"{prefix}{_column_of(model_cls, field_name)}")

            read[field_name] = {target_key: held} if held is not None and target_key else None

            continue

        if field_name.startswith("extra_") and "extra" in model_cls.meta.fields:
            read[field_name] = _serialized(_extra_values(mapping, model_cls, prefix).get(field_name[6:]))

            continue

        if is_computed_field(model_cls, field_name):
            read[field_name] = _serialized(_computed_value(mapping, model_cls, field_name, path, tables))

            continue

        read[field_name] = _serialized(mapping.get(f"{prefix}{_column_of(model_cls, field_name)}"))

    return read


def _extra_values(mapping: Any, model_cls: Any, prefix: str) -> dict[str, Any]:
    """What the custom fields of a row hold, whatever the driver made of the
    JSON column: a mapping, a string, or nothing at all."""
    import json

    held = mapping.get(f"{prefix}{_column_of(model_cls, 'extra') or 'extra'}")

    if isinstance(held, str):
        try:
            held = json.loads(held)
        except ValueError:
            return {}

    return held if isinstance(held, dict) else {}


def _serialized(value: Any) -> Any:
    """What ``model_dump`` makes of a moment, said the same way here: a row
    carries the type the driver read, the answer carries what the API says."""
    from datetime import date, datetime, time

    from fastedgy.serializers import datetime_serializer

    if isinstance(value, datetime):
        return datetime_serializer(value)

    if isinstance(value, (date, time)):
        return value.isoformat()

    return value


async def read_rows(
    query: QuerySet, map_fields: dict[str, Any], seen_by: frozenset[str] | None = None
) -> tuple[list[dict[str, Any]], list[Any]]:
    """The rows of ``query``, serialized by the selection alone, and a view of
    each row for whoever was named by ``seen_by``.

    The caller has checked :func:`can_read_rows` and what the hooks receiving an
    item said they read.
    """
    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry

    expression, tables = await query.as_select_with_tables()
    rows = await get_service(Registry).database.fetch_all(expression)
    reads = [_read_level(row._mapping, query.model_class, map_fields, "", tables) or {} for row in rows]

    for field_name, value in map_fields.items():
        if isinstance(value, list):
            await _attach_to_many(query.model_class, reads, field_name, value[0])

    allowed = _allowed_tree(seen_by) if seen_by is not None else None
    seen = (
        [_RowValues(row._mapping, query.model_class, "", tables, allowed) for row in rows]
        if allowed is not None
        else []
    )

    return reads, seen


async def _attach_to_many(
    model_cls: Any, reads: list[dict[str, Any]], field_name: str, sub_map: dict[str, Any]
) -> None:
    """Read a to-many relation for the whole page, and hand each row its share.

    One query for the page, whatever it holds: the rows of the link table carry
    the key of their owner, which is what groups them.
    """
    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry
    from fastedgy.orm.field_selector import (
        _inject_relation_default_order,
        _relation_order_fields,
        _target_default_order,
        apply_field_map_optimizations,
    )

    plan = _to_many_of(model_cls, field_name)
    owner_key_name = find_primary_key_field(_real_model_cls(model_cls))

    if plan is None or owner_key_name is None:
        return

    holder, owner_key, target_key, target = plan
    owned = [read[owner_key_name] for read in reads if read.get(owner_key_name) is not None]

    for read in reads:
        read[field_name] = []

    if not owned:
        return

    order_by = _target_default_order(target)
    kept = {name: True for name in _relation_order_fields(order_by)}
    selection: dict[str, Any] = {owner_key: {owner_key_name: True}}

    if target_key:
        selection[target_key] = {**kept, **sub_map}
        order_by = cast("OrderByList", [(f"{target_key}.{name}", direction) for name, direction in order_by])
    else:
        selection = {**selection, **kept, **sub_map}

    query: Any = holder.meta.managers["query_related"].get_queryset()
    query = query.filter(**{f"{owner_key}__{owner_key_name}__in": owned})
    query = _inject_relation_default_order(apply_field_map_optimizations(query, selection), order_by)

    expression, tables = await query.as_select_with_tables()
    rows = await get_service(Registry).database.fetch_all(expression)
    shares: dict[Any, list[Any]] = {}

    for row in rows:
        mapping = row._mapping
        owner = mapping.get(_column_of(_real_model_cls(holder), owner_key) or "")
        share = _read_level(mapping, target, sub_map, target_key or "", tables)

        if owner is None or share is None:
            continue

        held = shares.setdefault(owner, [])

        if len(held) < _READ_LIMIT:
            held.append(share)

    for read in reads:
        read[field_name] = shares.get(read.get(owner_key_name), [])

    # A relation of that relation is read the same way, once for everything the
    # page holds of it.
    gathered = [share for held in shares.values() for share in held]

    for name, value in sub_map.items():
        if isinstance(value, list) and gathered:
            await _attach_to_many(target, gathered, name, value[0])
