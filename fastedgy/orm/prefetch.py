# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Edgy's ``Prefetch``, with its batched read fixed for the rows it serves.

Edgy reads a prefetch for a whole batch of rows in one query, then hands each
row its share, and two things go wrong on the way.

It hands the prefetch to every model built from a row, the models joined into
it included, and bakes it for whichever arrives first: joined rows reaching it
first, the batch ends up keyed by their model and the rows that own the
relation find nothing under their own keys. The bake is held here per model,
and a model that does not carry the relation is answered without one.

What a row then finds missing, Edgy reads again row by row, which is the N+1
the prefetch was there to avoid, and on a many-to-many it filters the target on
the name of the relation, a column the target does not carry. The batch covers
every row it was built from, so a key it does not hold is an empty relation and
is answered as such.

TODO: drop once Edgy bakes per model and answers an empty relation itself
(still both in 0.36.1).
"""

import asyncio
from collections import defaultdict
from typing import Any

from edgy.core.db.querysets.prefetch import Prefetch

_init_bake = Prefetch.init_bake


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


__all__ = [
    "Prefetch",
]
