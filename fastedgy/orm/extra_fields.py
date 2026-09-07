# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from functools import cache
from time import monotonic
from typing import TYPE_CHECKING, Any, NoReturn, cast

from sqlalchemy import String

from fastedgy.models.extra_field_model import WorkspaceExtraFieldModel

if TYPE_CHECKING:
    from fastedgy.models.workspace_extra_field import BaseWorkspaceExtraField

logger = logging.getLogger("fastedgy.extra_fields")

EXTRA_FIELD_PREFIX = "extra_"


def has_extra_fields(model_cls: Any) -> bool:
    return "extra" in model_cls.meta.fields


def has_extendable_models() -> bool:
    """Whether any model holds the `extra` column.

    False is the answer for every application that does not use custom fields,
    and it makes the whole feature free: nothing can be declared against
    anything, so nothing is worth looking up or loading."""
    return bool(WorkspaceExtraFieldModel.__members__)


@cache
def extendable_models() -> dict[str, Any]:
    """The models a workspace may add a field to, by the name their metadata
    carries: the ones holding the `extra` column, and nothing to declare.

    Cached: the registry is settled once the models are imported."""
    from fastedgy.dependencies import get_service
    from fastedgy.metadata_model.generator import generate_metadata_name
    from fastedgy.orm import Registry

    models: dict[str, Any] = {}

    for model in get_service(Registry).models.values():
        meta = getattr(model, "meta", None)

        if not isinstance(model, type) or meta is None or meta.abstract or not has_extra_fields(model):
            continue

        if getattr(model, "__is_proxy_model__", False):
            continue

        models[generate_metadata_name(model)] = model

    return models


def check_extra_value(declared: Any, key: str, value: Any) -> None:
    """Refuse a value that does not match the type the workspace declared.

    An agent filling a hundred records writes "excellent", "Excellent" and
    "exelent" unless something stops it, and a date field would otherwise take
    "banana"."""
    from pydantic import ValidationError

    from fastedgy.i18n import _t
    from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType

    if value is None:
        if getattr(declared, "required", False):
            _refuse(key, _t("a value"))

        return

    field_type = getattr(declared, "field_type", None)

    if field_type == WorkspaceExtraFieldType.choice:
        values = declared.option_values()

        if not isinstance(value, str) or value not in values:
            _refuse(key, _t("one of these values: {values}", values=", ".join(values) or "-"))

        return

    field = _extra_field_instance(field_type)

    if field is None:
        return

    # `bool` is an `int` in Python, and pydantic follows: without this guard
    # `true` would pass for an integer and be stored as one.
    if isinstance(value, bool) and field.annotation is not bool:
        _refuse(key, str(_extra_type_label(field_type)))

    try:
        _extra_validator(field_type).validate_python(value)
    except ValidationError:
        _refuse(key, str(_extra_type_label(field_type)))


def _extra_type_label(field_type: Any) -> Any:
    return getattr(field_type, "value", field_type)


def _refuse(key: str, expected: Any) -> NoReturn:
    from fastapi import HTTPException

    from fastedgy.i18n import _t

    raise HTTPException(
        status_code=422,
        detail=_t("The field {field} expects {expected}.", field=key, expected=expected),
    )


@cache
def _extra_validator(field_type: Any) -> Any:
    """One validator per type, built once: compiling it costs some twenty times
    the validation it then performs, and a write carries as many values as the
    workspace declared fields."""
    from pydantic import TypeAdapter

    return TypeAdapter(_extra_field_instance(field_type).annotation)


@cache
def _extra_field_instance(field_type: Any) -> Any:
    from fastedgy.models.workspace_extra_field import EXTRA_FIELD_TYPE_OPTIONS, EXTRA_FIELDS_MAP

    field_class = EXTRA_FIELDS_MAP.get(field_type)

    if field_class is None:
        return None

    return field_class(**EXTRA_FIELD_TYPE_OPTIONS.get(field_type, {}))


@cache
def find_workspace_extra_field_model() -> "type[BaseWorkspaceExtraField] | None":
    """The concrete extra-field model of the app (e.g. WorkspaceExtraField) is
    not necessarily registered under that name: resolve it by base class.

    Cached, because this walks every registered model and the answer cannot
    change once they are imported. None when the app declares none."""
    from fastedgy.dependencies import get_service
    from fastedgy.models.workspace_extra_field import BaseWorkspaceExtraField
    from fastedgy.orm import Registry

    for model in get_service(Registry).models.values():
        if (
            isinstance(model, type)
            and issubclass(model, BaseWorkspaceExtraField)
            and not getattr(model, "__is_proxy_model__", False)
            and not model.meta.abstract
        ):
            return cast("type[BaseWorkspaceExtraField]", model)

    return None


@cache
def _warn_when_nothing_is_extendable() -> None:
    """Said once, at the first request: an application that declares custom
    fields but opens no model to them would otherwise see the feature do
    nothing at all, without a word."""
    if find_workspace_extra_field_model() is None:
        return

    logger.warning(
        "A workspace extra field model is declared but no model holds the `extra` column: "
        "custom fields cannot be declared against anything. Add `ExtendableMixin` to the "
        "models meant to accept them."
    )


# What each workspace declared, by workspace id, with the moment it was read.
_cached_extra_fields: dict[Any, tuple[float, list[Any]]] = {}

_CACHE_SWEEP_AT = 500


_invalidator: Any = None


def watch_workspace_extra_fields(invalidator: Any) -> None:
    """Name the listener whose health decides whether a cached copy is worth
    anything. None goes back to reading on every entry."""
    global _invalidator

    _invalidator = invalidator

    invalidate_workspace_extra_fields()


def workspace_extra_fields_are_watched() -> bool:
    return _invalidator is not None and _invalidator.listening


async def announce_workspace_extra_fields(workspace_id: Any) -> None:
    """Tell every other process to forget what it read for this workspace.

    Sent on the connection that carries the write, so it only reaches anyone
    once the transaction commits: nobody re-reads a row that never landed."""
    from sqlalchemy import text

    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry

    settings = get_service(BaseSettings)

    if settings.workspace_extra_field_cache_seconds <= 0:
        return

    sql = text("SELECT pg_notify(:channel, :payload)")

    await get_service(Registry).database.execute(
        sql.bindparams(channel=settings.workspace_extra_field_notify_channel, payload=str(workspace_id))
    )


def invalidate_workspace_extra_fields(workspace_id: Any = None) -> None:
    """Forget what was read for a workspace, or for all of them.

    Called by the extra field model on every write, so a worker never serves
    from its own stale copy."""
    if workspace_id is None:
        _cached_extra_fields.clear()
    else:
        _cached_extra_fields.pop(workspace_id, None)


async def _read_workspace_extra_fields(model_cls: Any, workspace_id: Any) -> list[Any]:
    """The fields of a workspace, read at most once per cache window.

    Entering a workspace happens on every request, and the fields change a few
    times a year: reading them each time is a round-trip paid for nothing. A
    write from this worker drops the entry at once; one from another worker is
    seen when the window closes.
    """
    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service

    window = get_service(BaseSettings).workspace_extra_field_cache_seconds

    # Never trusted without the channel that keeps it in step: a listener that
    # could not be opened, or that just died, means reading every time again.
    if window <= 0 or not workspace_extra_fields_are_watched():
        return await model_cls.query.all()

    cached = _cached_extra_fields.get(workspace_id)
    now = monotonic()

    if cached is not None and now - cached[0] < window:
        return cached[1]

    fields = await model_cls.query.all()

    # A workspace that stops being served would otherwise keep its entry for
    # the life of the process: past a few hundred, the expired ones go.
    if len(_cached_extra_fields) > _CACHE_SWEEP_AT:
        for key in [key for key, (read_at, _) in _cached_extra_fields.items() if now - read_at >= window]:
            del _cached_extra_fields[key]

    _cached_extra_fields[workspace_id] = (now, fields)

    return fields


async def load_workspace_extra_fields() -> None:
    """Put the fields the current workspace declared into the request context.

    Called wherever a workspace is entered — the `/{workspace}` dependency, the
    MCP `enter_workspace`, a shared record, a queued task — so every path reads
    the same fields from the same place."""
    from fastedgy import context

    if not has_extendable_models():
        _warn_when_nothing_is_extendable()

        return

    workspace = context.get_workspace()

    if context.get_request() is None or workspace is None:
        return

    model_cls = find_workspace_extra_field_model()

    if model_cls is None:
        return

    context.set_workspace_extra_fields(await _read_workspace_extra_fields(model_cls, workspace.id))


def declared_extra_fields(model_cls: Any) -> dict[str, Any]:
    if not has_extra_fields(model_cls):
        return {}

    from fastedgy import context
    from fastedgy.metadata_model.generator import generate_metadata_name

    return context.get_map_workspace_extra_fields(generate_metadata_name(model_cls))


def extra_field_column(model_cls: Any, field_path: str) -> Any | None:
    """The SQL expression reading `extra_<name>` out of the JSON column.

    ``->>`` always yields text, so the column is cast to the type the workspace
    declared — otherwise a comparison against an already-converted value fails
    outright (``text = integer``), and ordering would put "10" before "2". The
    type comes from the field class the declared type maps to, and a text one is
    left alone: casting it back to ``varchar(n)`` would silently truncate."""
    from sqlalchemy import cast as sa_cast

    if "." in field_path or not field_path.startswith(EXTRA_FIELD_PREFIX):
        return None

    declared = declared_extra_fields(model_cls)
    name = field_path[len(EXTRA_FIELD_PREFIX) :]

    if name not in declared:
        return None

    column = model_cls.columns.extra.op("->>")(name)
    field = _extra_field_instance(declared[name].field_type)
    sql_type = getattr(field, "column_type", None)

    if sql_type is None or isinstance(sql_type, String):
        return column

    return sa_cast(column, sql_type)


def pop_extra_field_values(model_cls: Any, data: dict[str, Any]) -> dict[str, Any]:
    from fastapi import HTTPException

    keys = [key for key in data if key.startswith(EXTRA_FIELD_PREFIX)]

    if not keys:
        return {}

    declared = declared_extra_fields(model_cls)
    values: dict[str, Any] = {}

    for key in keys:
        name = key[len(EXTRA_FIELD_PREFIX) :]
        value = data.pop(key)

        if name not in declared:
            raise HTTPException(status_code=422, detail=f"Unknown extra field '{key}'")

        check_extra_value(declared[name], key, value)

        values[name] = value

    return values


def merge_extra_field_values(current: Any, values: dict[str, Any]) -> dict[str, Any]:
    return {**(current or {}), **values}


__all__ = [
    "EXTRA_FIELD_PREFIX",
    "check_extra_value",
    "declared_extra_fields",
    "extendable_models",
    "extra_field_column",
    "find_workspace_extra_field_model",
    "has_extendable_models",
    "has_extra_fields",
    "announce_workspace_extra_fields",
    "invalidate_workspace_extra_fields",
    "load_workspace_extra_fields",
    "merge_extra_field_values",
    "pop_extra_field_values",
    "watch_workspace_extra_fields",
    "workspace_extra_fields_are_watched",
]
