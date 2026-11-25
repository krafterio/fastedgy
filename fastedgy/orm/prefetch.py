# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Edgy's ``Prefetch``, with its batched read fixed for the rows it serves.

Edgy reads a prefetch for a whole batch of rows in one query, then hands each
row its share, and two things go wrong on the way.

It hands the prefetch to every model built from a row, the models joined into
it included, and bakes it for whichever arrives first: joined rows reaching it
first, the batch ends up keyed by their model and the rows that own the
relation find nothing under their own keys. The bake is held here per model,
and a model that does not carry the relation is answered without one. Outside
a batch, a record read alone, the joined model reads the relation as its own
and fails on a field it does not carry: a prefetch names a relation of the
model queried, so a model joined into its row is left out of it.

What a row then finds missing, Edgy reads again row by row, which is the N+1
the prefetch was there to avoid, and on a many-to-many it filters the target on
the name of the relation, a column the target does not carry. The batch covers
every row it was built from, so a key it does not hold is an empty relation and
is answered as such.

The batch read also names every row of the batch in a bound parameter of its
own, and PostgreSQL takes 32767 of them at most: a list longer than that failed
before it read anything. The batch is read here in chunks, merged into the one
prefetch the rows are handed.

TODO: drop once Edgy bakes per model, answers an empty relation itself, keeps a
prefetch to the model queried and bounds the parameters of its batch read
(still all four in 0.36.1).
"""

import asyncio
from collections import defaultdict
from typing import Any

from edgy.core.db.models.mixins.row import ModelRowMixin
from edgy.core.db.querysets.executor import QueryExecutor
from edgy.core.db.querysets.prefetch import Prefetch

PREFETCH_CHUNK_SIZE = 5000


class _BakedResults(dict):
    """What the batch read, and an empty list for a row it read nothing for."""

    def __contains__(self, key: object) -> bool:
        return True

    def __missing__(self, key: object) -> list:
        return []


_NOTHING = _BakedResults()


def _carries_relation(model_class: Any, related_name: str) -> bool:
    fields = getattr(getattr(model_class, "meta", None), "fields", {})

    return related_name.split("__", 1)[0] in fields


async def _init_bake(self: Prefetch, model_class: Any) -> None:
    if self._baked or not self._is_finished or self.queryset is None:
        return

    self._baked = True

    for queryset in self.__dict__.get("_fs_chunks") or [self.queryset]:
        async for result in queryset._execute_iterate(True):
            model_key = model_class.create_model_key_from_sqla_row(queryset._current_row, row_prefix=self._bake_prefix)
            self._baked_results[model_key].append(result)


async def _shared_init_bake(self: Prefetch, model_class: Any) -> None:
    # Nothing was prepared for a batch: the row reads its own relation, as it
    # does outside a list.
    if not self._is_finished:
        await _init_bake(self, model_class)

        return

    baked: dict[Any, Any] = self.__dict__.setdefault("_fs_baked", {})
    lock: asyncio.Lock = self.__dict__.setdefault("_fs_bake_lock", asyncio.Lock())

    # Held for the read too: the caller reads the results as soon as this
    # returns, and another model must not swap them in between.
    async with lock:
        if model_class not in baked:
            if _carries_relation(model_class, self.related_name):
                self._baked = False
                self._baked_results = defaultdict(list)
                await _init_bake(self, model_class)
                baked[model_class] = _BakedResults(self._baked_results)
            else:
                baked[model_class] = _NOTHING

        self._baked_results = baked[model_class]


Prefetch.init_bake = _shared_init_bake  # type: ignore[method-assign]


_prepare_prefetches_for_batch = QueryExecutor._prepare_prefetches_for_batch


async def _chunked_prefetches_for_batch(self: QueryExecutor, batch: Any, tables_and_models: Any) -> list[Prefetch]:
    if len(batch) <= PREFETCH_CHUNK_SIZE:
        return await _prepare_prefetches_for_batch(self, batch, tables_and_models)

    chunks = [
        await _prepare_prefetches_for_batch(self, batch[start : start + PREFETCH_CHUNK_SIZE], tables_and_models)
        for start in range(0, len(batch), PREFETCH_CHUNK_SIZE)
    ]
    prefetches = chunks[0]

    for index, prefetch in enumerate(prefetches):
        prefetch.__dict__["_fs_chunks"] = [chunk[index].queryset for chunk in chunks]

    return prefetches


QueryExecutor._prepare_prefetches_for_batch = _chunked_prefetches_for_batch  # type: ignore[method-assign]


_handle_prefetch_related = ModelRowMixin._ModelRowMixin__handle_prefetch_related.__func__  # type: ignore[attr-defined]


async def _handle_own_prefetch_related(cls: Any, *, prefix: str, **kwargs: Any) -> None:
    # The model queried is built without a prefix, a joined one under its path.
    if not prefix:
        await _handle_prefetch_related(cls, prefix=prefix, **kwargs)


ModelRowMixin._ModelRowMixin__handle_prefetch_related = classmethod(_handle_own_prefetch_related)  # type: ignore[attr-defined]


__all__ = [
    "Prefetch",
]
