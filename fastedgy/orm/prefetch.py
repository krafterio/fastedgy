# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Edgy's ``Prefetch``, with its batched read shared by the models it serves.

Edgy reads a prefetch for a whole batch of rows in one query, then hands each
model its share. The models of a batch are built concurrently, and the first
one to reach the prefetch flags it baked before its query has returned: the
others find no result yet and read their relation one by one, which is the
N+1 the prefetch was there to avoid. The first model to arrive runs the read
here, the others wait for it.

TODO: drop once Edgy awaits its own bake (still racing in 0.36.1).
"""

import asyncio
from typing import Any

from edgy.core.db.querysets.prefetch import Prefetch

_init_bake = Prefetch.init_bake


async def _shared_init_bake(self: Prefetch, model_class: Any) -> None:
    lock = getattr(self, "_fs_bake_lock", None)

    if lock is None:
        lock = asyncio.Lock()
        self._fs_bake_lock = lock  # type: ignore[attr-defined]

    async with lock:
        await _init_bake(self, model_class)


Prefetch.init_bake = _shared_init_bake  # type: ignore[method-assign]


__all__ = [
    "Prefetch",
]
