# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Batch reloading for column-pruned querysets.

The field selector prunes unselected columns with ``defer()``. Any consumer
(view transformers, application code) may still read a pruned attribute: Edgy
would then lazy-load the row — one query PER instance (N+1). This module makes
that access transparent again: instances materialized by a pruned queryset
share a batch handle, and the first deferred access reloads the full rows of
the WHOLE batch in a single query.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastedgy.orm.query import QuerySet
from fastedgy.orm.utils import find_primary_key_field

_BATCH_ATTR = "_fs_deferred_batch"

_batch_queryset_classes: dict[type, type] = {}


class _DeferredBatchQuerySetMixin:
    async def _execute_all(self) -> list[Any]:
        items = await super()._execute_all()  # type: ignore[misc]

        if items and getattr(self, "_defer", None):
            batch: dict[str, Any] = {
                "model_cls": self.model_class,  # type: ignore[attr-defined]
                "instances": list(items),
                "future": None,
            }

            for item in items:
                object.__setattr__(item, _BATCH_ATTR, batch)

        return items


def enable_deferred_batch_loading(query: QuerySet) -> QuerySet:
    """Swap the queryset class for a batch-aware subclass. ``_clone`` preserves
    ``__class__``, so the behavior survives any later chaining."""
    base_cls = type(query)

    if issubclass(base_cls, _DeferredBatchQuerySetMixin):
        return query

    mixed = _batch_queryset_classes.get(base_cls)

    if mixed is None:
        mixed = type(f"DeferredBatch{base_cls.__name__}", (_DeferredBatchQuerySetMixin, base_cls), {})
        _batch_queryset_classes[base_cls] = mixed

    query.__class__ = mixed

    return query


async def consume_batch_load(instance: Any) -> bool:
    """Reload the deferred columns for the whole batch of ``instance`` in one
    query. Returns True when the instance was hydrated this way; False when the
    caller must fall back to the regular per-row load."""
    batch = instance.__dict__.get(_BATCH_ATTR)

    if batch is None:
        return False

    future = batch.get("future")

    if future is None:
        future = asyncio.ensure_future(_fetch_and_merge(batch))
        batch["future"] = future

    hydrated_by_pk = await future
    primary_key = find_primary_key_field(batch["model_cls"])

    return primary_key is not None and instance.__dict__.get(primary_key) in hydrated_by_pk


async def _fetch_and_merge(batch: dict[str, Any]) -> set[Any]:
    model_cls = batch["model_cls"]
    instances = batch["instances"]
    primary_key = find_primary_key_field(model_cls)

    if primary_key is None:
        return set()

    ids = [instance.__dict__.get(primary_key) for instance in instances]
    ids = [pk for pk in ids if pk is not None]

    if not ids:
        return set()

    # The rows were already authorized/filtered by the original query: reload
    # through the unfiltered manager so guards and global filters (workspace,
    # visibility) cannot diverge from the batch content.
    manager = getattr(model_cls, "global_query", None) or model_cls.query
    full_rows = await manager.filter(**{f"{primary_key}__in": ids}).all()
    by_pk = {row.__dict__.get(primary_key): row for row in full_rows}

    hydrated: set[Any] = set()

    for instance in instances:
        source = by_pk.get(instance.__dict__.get(primary_key))

        if source is None:
            continue

        for key, value in source.__dict__.items():
            if key not in instance.__dict__:
                instance.__dict__[key] = value

        hydrated.add(instance.__dict__.get(primary_key))

    return hydrated


__all__ = [
    "consume_batch_load",
    "enable_deferred_batch_loading",
]
