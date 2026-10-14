# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""What a request may read of the records a read reaches through its relations.

A to-one relation is joined, and a link table walked, without the rules of the
model they land on: a row hands over the record it points at whatever that
record's own global filters and access guards say, a record the request is
refused on its own route. What a read reaches is therefore asked of each model's
own query, once per model for the whole read, and what the request may not read
leaves the answer: a to-one relation keeps its key alone, a to-many relation
drops the record.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from fastedgy.dependencies import get_service
from fastedgy.orm.access_guard import AccessDeniedError, ModelAccessGuardRegistry, ModelAction, check_access
from fastedgy.orm.filter import R
from fastedgy.orm.filter.global_filters import GlobalFilterRegistry
from fastedgy.orm.utils import find_primary_key_field


def _real_model_cls(model_cls: Any) -> Any:
    if getattr(model_cls, "__is_proxy_model__", False):
        return getattr(model_cls, "__parent__", None) or model_cls

    return model_cls


def narrows_within_scope(model_cls: type) -> bool:
    """Whether a global filter reads a model narrower than its scope.

    The filters every workspaceable model carries are the scope itself and
    narrow nothing within it: the workspace filter, and the confinement to a
    shared record, which only holds inside a shared-record context. Their
    cascade does narrow, for a model under a shareable root.
    """
    from fastedgy.models.mixins import _workspace_filter_applies
    from fastedgy.orm.workspace_shareable import (
        WorkspaceShareableRegistry,
        shared_record_cascade_filter,
        shared_record_confinement_filter,
    )

    for gf in get_service(GlobalFilterRegistry).get_filters(model_cls):
        if gf.apply is _workspace_filter_applies or gf.get_filter is shared_record_confinement_filter:
            continue

        if gf.get_filter is not shared_record_cascade_filter:
            return True

        shareable = get_service(WorkspaceShareableRegistry)

        if any(shareable.path_for(model_cls, root.key) not in (None, "id") for root in shareable.roots().values()):
            return True

    return False


def is_guarded(model_cls: type) -> bool:
    """Whether a member of a scope may be refused a record the scope holds.

    A global filter or an access guard reads a model narrower than its scope:
    what is said about one of its records has to reach the members who can read
    it, and no one else.
    """
    return narrows_within_scope(model_cls) or get_service(ModelAccessGuardRegistry).has_guards(model_cls)


async def unreadable_keys(model_cls: type, keys: Iterable[Any]) -> set[Any]:
    """The keys, among [keys], of the records of [model_cls] the request may not read.

    A model only an access guard narrows is read whole or not at all, which the
    guard answers without the database; a narrowing filter is asked once, for
    all the keys, through the model's own query.
    """
    wanted = {key for key in keys if key is not None}
    model_cls = _real_model_cls(model_cls)

    if not wanted or not is_guarded(model_cls):
        return set()

    try:
        if not narrows_within_scope(model_cls):
            check_access(model_cls, ModelAction.read)

            return set()

        key_name = find_primary_key_field(model_cls) or "id"
        rows = await model_cls.query.filter(R(key_name, "in", list(wanted))).only(key_name).all()
    except AccessDeniedError:
        return wanted

    return wanted - {getattr(row, key_name, None) for row in rows}


class Readable:
    """What the request reads of the records a read reaches, asked once per record.

    For a read walking instances rather than a serialized selection: [ask] puts
    the question for many keys at once, [hides] answers for one, asking on a
    miss.
    """

    def __init__(self) -> None:
        self._asked: dict[Any, set[Any]] = {}
        self._hidden: dict[Any, set[Any]] = {}

    async def ask(self, model_cls: Any, keys: Iterable[Any]) -> None:
        model_cls = _real_model_cls(model_cls)
        asked = self._asked.setdefault(model_cls, set())
        fresh = {key for key in keys if key is not None and key not in asked}

        if not fresh:
            return

        asked |= fresh
        self._hidden.setdefault(model_cls, set()).update(await unreadable_keys(model_cls, fresh))

    async def hides(self, model_cls: Any, key: Any) -> bool:
        await self.ask(model_cls, [key])

        return key in self._hidden.get(_real_model_cls(model_cls), ())

    async def ask_reached(self, model_cls: Any, items: Sequence[Any], paths: Iterable[str]) -> None:
        """Put the question for the records [paths] reach from [items] through the
        to-one relations already loaded on them, once per model. A to-many
        relation is read later, and asked then."""
        for path in paths:
            current_model = _real_model_cls(model_cls)
            reached = list(items)

            for part in path.split(".")[:-1]:
                field = current_model.meta.fields.get(part)
                target = relation_target(field)

                if target is None or getattr(field, "is_m2m", False) or hasattr(field, "related_from"):
                    break

                reached = [value for value in (getattr(item, part, None) for item in reached) if value is not None]
                await self.ask(target, [getattr(value, "pk", None) for value in reached])
                current_model = _real_model_cls(target)


def relation_target(field: Any) -> Any:
    """The model a relation reaches, or None for a column or a generic reference,
    whose target loads through its own query already."""
    if field is None or getattr(field, "is_generic_foreign_key", False):
        return None

    return getattr(field, "target", None) or getattr(field, "related_from", None)


async def confine_reads(model_cls: Any, reads: list[dict[str, Any]], map_fields: dict[str, Any]) -> None:
    """Narrow serialized [reads] of [model_cls] to what the request may read of
    the records their selected relations reach, level by level.

    A to-one relation asked for its key alone says nothing the row does not, and
    is left as it is. A reverse relation is read through the related model's own
    query, narrowed already: only what its records reach is asked. A link table
    is walked unfiltered, so a many-to-many relation is asked, its keys included.
    """
    model_cls = _real_model_cls(model_cls)

    for name, selection in map_fields.items():
        if not isinstance(selection, (dict, list)):
            continue

        field = model_cls.meta.fields.get(name)
        target = relation_target(field)

        if target is None:
            continue

        key_name = find_primary_key_field(_real_model_cls(target)) or "id"
        to_many = isinstance(selection, list)
        sub_map = selection[0] if to_many else selection

        if not to_many and set(sub_map) <= {key_name}:
            continue

        held = [
            share
            for read in reads
            for share in ((read.get(name) or []) if to_many else [read.get(name)])
            if isinstance(share, dict)
        ]
        asked = not to_many or getattr(field, "is_m2m", False)
        hidden = await unreadable_keys(target, (share.get(key_name) for share in held)) if asked else set()

        if hidden:
            for read in reads:
                share = read.get(name)

                if to_many and isinstance(share, list):
                    read[name] = [
                        item for item in share if not isinstance(item, dict) or item.get(key_name) not in hidden
                    ]
                elif isinstance(share, dict) and share.get(key_name) in hidden:
                    read[name] = {key_name: share[key_name]}

        await confine_reads(target, [share for share in held if share.get(key_name) not in hidden], sub_map)


__all__ = [
    "Readable",
    "confine_reads",
    "is_guarded",
    "narrows_within_scope",
    "relation_target",
    "unreadable_keys",
]
