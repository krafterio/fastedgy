# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from typing import Any, TypeVar

from fastedgy import context
from fastedgy.dependencies import get_service, has_service
from fastedgy.metadata_model.generator import generate_metadata_name
from fastedgy.orm.signals import post_delete, post_save
from fastedgy.orm.transaction import run_signal_side_effect
from fastedgy.realtime.broadcaster import WebSocketBroadcaster

logger = logging.getLogger("fastedgy.realtime.model")

M = TypeVar("M", bound=type)

# What a write can be, and what a client hears: `engram.created`,
# `fragment.updated`, `fragment.deleted`.
ACTIONS = ("create", "update", "delete")

EVENTS = {"create": "created", "update": "updated", "delete": "deleted"}

# A to-many that fans out further than this announces itself on the model's own
# channel alone: naming every related record would make the message larger than
# a NOTIFY carries, and a list refreshing is what such a write means anyway.
MAX_RELATION_CHANNELS = 50

# Which running instance of a client made a write, when it says so, and what an
# announcement carries back so that instance can recognise its own echo.
ORIGIN_HEADER = "X-Origin-Id"

# An origin travels in a NOTIFY payload, where an oversized one would push the
# announcement past what Postgres carries and cost it its channels, serving the
# whole workspace instead of the sockets that asked. It is a client-supplied
# string: capped here, and only ever compared, never trusted.
MAX_ORIGIN_LENGTH = 64


class RealtimeRegistry:
    """Which models announce their writes, which of their writes, and with what.

    A model says so for itself, through [realtime_model]. Nothing is announced
    by default: an event nobody is watching for is a NOTIFY, a wake-up on every
    worker and a frame on every socket of the workspace.
    """

    def __init__(self) -> None:
        self._actions: dict[str, dict[str, bool]] = {}
        self._fields: dict[str, dict[str, str]] = {}
        self._relations: dict[str, list[str]] = {}
        self._classes: dict[str, type] = {}
        self._addressing: dict[str, tuple[str, str | None]] = {}

    def register(
        self,
        model_cls: type,
        actions: dict[str, bool],
        fields: list[str] | dict[str, str] | None = None,
        relations: list[str] | None = None,
        workspace_field: str = "workspace",
        user_field: str | None = None,
    ) -> str:
        unknown = set(actions) - set(ACTIONS)

        if unknown:
            raise ValueError(f"Unknown realtime actions {sorted(unknown)}, expected any of {list(ACTIONS)}")

        name = generate_metadata_name(model_cls)
        self._actions[name] = {action: actions.get(action, True) for action in ACTIONS}
        self._fields[name] = dict(fields) if isinstance(fields, dict) else {field: field for field in fields or []}
        self._relations[name] = list(relations or [])
        self._classes[name] = model_cls
        self._addressing[name] = (workspace_field, user_field)

        return name

    def is_enabled(self, model: str, action: str) -> bool:
        return self._actions.get(model, {}).get(action, False)

    def actions(self, model: str) -> dict[str, bool]:
        return dict(self._actions.get(model, {}))

    def fields(self, model: str) -> dict[str, str]:
        return dict(self._fields.get(model, {}))

    def relations(self, model: str) -> list[str]:
        return list(self._relations.get(model, []))

    def addressing(self, model: str) -> tuple[str, str | None]:
        """Which column names the workspace an event belongs to, and which names
        the account it belongs to instead."""
        return self._addressing.get(model, ("workspace", None))

    def model_class(self, model: str) -> type | None:
        return self._classes.get(model)

    def models(self) -> list[str]:
        return sorted(self._actions)


registry = RealtimeRegistry()


def realtime_model(
    actions: dict[str, bool] | None = None,
    fields: list[str] | dict[str, str] | None = None,
    relations: list[str] | None = None,
    workspace_field: str = "workspace",
    user_field: str | None = None,
    **kwargs: bool,
):
    """Announce this model's writes to the clients watching them.

    Two channels carry each write: the model, which a list subscribes to so it
    can refresh, and `model:id`, which whoever is reading that record subscribes
    to. Only identifiers travel; the client reads the record back through the
    API.

    An action can be turned off, by name:

        @realtime_model(delete=False)
        class Engram(...): ...

    [fields] names the columns to carry alongside the identifiers, so a client
    can tell whether an event is any of its business without reading the record
    first. A list keeps the column names, a dict renames them:

        @realtime_model(fields=["record_model", "record_id"])
        @realtime_model(fields={"engram_id": "engram"})

    A foreign key gives its id, and nothing is read that the write did not
    carry: this runs on a row being inserted, or on one being deleted.

    [relations] names the relations whose own channel the event also reaches, so
    a page reading one record hears about what hangs off it without subscribing
    to every record of the other model:

        @realtime_model(relations=["engram"])       # a fragment reaches engram:3
        @realtime_model(relations=["record"])       # an attachment reaches fragment:9

    [workspace_field] names the column the event is addressed by, for a model
    that is its own tenant:

        @realtime_model(workspace_field="id")       # the workspace itself

    [user_field] addresses the event to one account instead of a workspace, for
    what belongs to a person rather than to a space. It reaches every socket
    that account holds, and no one else's:

        @realtime_model(user_field="id")            # the account itself
        @realtime_model(user_field="user")          # something of theirs

    Any relation kind answers: a foreign key and a generic foreign key from the
    values being written, a many-to-many or a reverse relation by reading the
    related rows, which costs a query per write and is why it is declared rather
    than assumed.
    """
    wanted = {**(actions or {}), **kwargs}

    def decorator(model_cls: M) -> M:
        model = registry.register(model_cls, wanted, fields, relations, workspace_field, user_field)

        @post_save.connect_via(model_cls)
        async def _on_save(
            sender: Any,
            instance: Any,
            model_instance: Any,
            is_update: bool,
            column_values: dict[str, Any],
            **_: Any,
        ) -> None:
            await _announce(model, "update" if is_update else "create", model_instance, column_values)

        @post_delete.connect_via(model_cls)
        async def _on_delete(sender: Any, instance: Any, model_instance: Any, **_: Any) -> None:
            await _announce(model, "delete", model_instance, {})

        return model_cls

    return decorator


async def _announce(model: str, action: str, model_instance: Any, column_values: dict[str, Any]) -> None:
    """Publish one write, once the transaction it belongs to has committed.

    What the announcement needs from the row is read here, inside the write's
    own transaction: a deleted record has lost its links by the time the
    announcement goes out. Only the publication is deferred, through
    [fastedgy.orm.transaction.run_signal_side_effect], which discards the queue
    of an attempt that rolled back. Under SERIALIZABLE a replayed transaction
    would otherwise announce once per attempt, and a write that never committed
    would announce all the same.

    A queryset write carries no instance and is not announced: it names no
    record, and the workspace it belongs to cannot be read back from it.
    """
    if model_instance is None or not registry.is_enabled(model, action):
        return

    # An application that did not turn realtime on pays nothing for a model that
    # carries the decorator: no NOTIFY, and no broadcaster brought into being to
    # issue one. The decorator says what a model would announce, `realtime=True`
    # says whether anything is listening.
    if not has_service(WebSocketBroadcaster):
        return

    record_id = getattr(model_instance, "id", None)

    if record_id is None:
        return

    event = EVENTS[action]
    label = f"realtime {model}.{event}"
    workspace_field, user_field = registry.addressing(model)
    extra = {key: _column(model_instance, column_values, column) for key, column in registry.fields(model).items()}
    meta = _meta(action, column_values)

    try:
        if user_field is not None:
            # Addressed to a person, not to a space: an account belongs to
            # several workspaces, and its own news is nobody else's.
            user_id = _column(model_instance, column_values, user_field)

            if user_id is None:
                return

            data = {"model": model, "id": record_id, **extra}

            run_signal_side_effect(
                lambda: get_service(WebSocketBroadcaster).broadcast_to_user(user_id, f"{model}.{event}", data, meta),
                label,
            )

            return

        workspace_id = _column(model_instance, column_values, workspace_field)

        if workspace_id is None:
            return

        channels = await _relation_channels(model, model_instance, column_values)

        run_signal_side_effect(
            lambda: get_service(WebSocketBroadcaster).broadcast_record(
                workspace_id, model, record_id, event, extra, channels, meta
            ),
            label,
        )
    except Exception as e:  # noqa: BLE001 - an announcement never fails the write it announces
        logger.warning("Could not announce %s.%s on %s: %s", model, event, record_id, e)


def _meta(action: str, column_values: dict[str, Any]) -> dict[str, Any]:
    """What is known about the write rather than about the record.

    `origin` names the client instance that made it, so that instance can leave
    its own echo alone instead of re-reading what it just wrote. `changed` names
    the columns the write moved, so a view that reads none of them has nothing
    to learn: only on an update, a row appearing or going being news to a list
    whatever its columns are.
    """
    meta: dict[str, Any] = {}
    origin = _origin()

    if origin is not None:
        meta["origin"] = origin

    if action == "update" and column_values:
        meta["changed"] = sorted(column_values)

    return meta


def _origin() -> str | None:
    """The client instance behind the request, as its own header names it."""
    request = context.get_request()
    value = request.headers.get(ORIGIN_HEADER) if request is not None else None

    return value if value and len(value) <= MAX_ORIGIN_LENGTH else None


async def _relation_channels(model: str, model_instance: Any, column_values: dict[str, Any]) -> list[str]:
    """The channels of the records this one hangs off, as it declared them."""
    relations = registry.relations(model)

    if not relations:
        return []

    model_cls = registry.model_class(model)
    fields = getattr(getattr(model_cls, "meta", None), "fields", {})
    channels: list[str] = []

    for name in relations:
        field = fields.get(name)

        if field is None:
            continue

        for target, target_id in await _related_records(field, name, model_instance, column_values):
            if target and target_id is not None:
                channels.append(f"{target}:{target_id}")

    if len(channels) > MAX_RELATION_CHANNELS:
        logger.info("Relation of %s fans out to %d records, announced on its own channel", model, len(channels))

        return []

    return channels


async def _related_records(
    field: Any,
    name: str,
    model_instance: Any,
    column_values: dict[str, Any],
) -> list[tuple[str | None, Any]]:
    """What a relation points at, as (model name, id) pairs.

    A generic foreign key already stores the target's name beside its id, a
    foreign key names it through the field, and a to-many has to be read. The
    read is guarded: an announcement is never worth failing the write it
    announces, and a row being deleted may have lost its links already.
    """
    model_column = getattr(field, "model_column", None)

    if model_column:
        return [
            (
                _column(model_instance, column_values, model_column),
                _column(model_instance, column_values, field.id_column),
            )
        ]

    is_m2m = getattr(field, "is_m2m", False)
    target = getattr(field, "target", None)

    if target is not None and not is_m2m:
        return [(generate_metadata_name(target), _column(model_instance, column_values, name))]

    if not is_m2m and not hasattr(field, "related_from"):
        return []

    related_model = _related_model(field)

    if related_model is None:
        return []

    try:
        # Ids rather than rows, and one more than what would be dropped anyway:
        # this runs inside the write's own transaction, so it is bounded before
        # it is read, not after.
        ids = await getattr(model_instance, name).limit(MAX_RELATION_CHANNELS + 1).values_list("id", flat=True)
    except Exception as e:  # noqa: BLE001 - a relation that cannot be read announces nothing
        logger.debug("Cannot read the relation %s to announce it: %s", name, e)

        return []

    return [(related_model, record_id) for record_id in ids]


def _related_model(field: Any) -> str | None:
    """The model on the other side of a to-many."""
    target = getattr(field, "target", None) or getattr(field, "related_from", None)

    return generate_metadata_name(target) if target is not None else None


def _column(model_instance: Any, column_values: dict[str, Any], name: str) -> Any:
    """One column of the record, read from the write before the record itself.

    During an insert the row is not there to be lazy-loaded yet, and the values
    being written hold what is needed. A foreign key gives its id: what travels
    names a record, it does not carry one.
    """
    value = column_values[name] if name in column_values else getattr(model_instance, name, None)

    return getattr(value, "id", value)


__all__ = [
    "ACTIONS",
    "EVENTS",
    "MAX_ORIGIN_LENGTH",
    "MAX_RELATION_CHANNELS",
    "ORIGIN_HEADER",
    "RealtimeRegistry",
    "realtime_model",
    "registry",
]
