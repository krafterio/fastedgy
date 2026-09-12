# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Answer a read from its rows, for the actions that only read.

The field selector prunes what a read selects; what still costs after it is the
model built for every row and for every relation joined into it. A read that
only reads has no use for them, and :mod:`fastedgy.orm.row_selector` serializes
the rows as they came back.

What stands in the way is a hook receiving items, since nothing can know what
it will reach for: the models are then built as they always were. A hook that
says what it reads with :func:`view_transformer_reads` is handed a view of its
own row instead, and the read keeps its speed.

An action asks :func:`plan_row_read` before optimizing its query, hands the
plan the columns its hooks read, and reads through it. No plan means the model
path, unchanged.
"""

from typing import Any

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    GetViewsTransformer,
    GetViewTransformer,
    view_transformer_reads_of,
)
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.orm.field_selector import parse_field_selector_input
from fastedgy.orm.query import QuerySet
from fastedgy.orm.row_selector import can_read_paths, can_read_rows, read_rows

__all__ = [
    "RowRead",
    "plan_row_read",
]


class RowRead:
    """A read its rows answer, and the hooks served from a row of it."""

    __slots__ = ("_map_fields", "_seen_by", "_view_hooks", "_views_hooks")

    def __init__(
        self,
        map_fields: dict[str, Any],
        seen_by: frozenset[str] | None,
        view_hooks: list[GetViewTransformer],
        views_hooks: list[GetViewsTransformer],
    ) -> None:
        self._map_fields = map_fields
        self._seen_by = seen_by
        self._view_hooks = view_hooks
        self._views_hooks = views_hooks

    @property
    def keep_fields(self) -> frozenset[str] | None:
        """What the hooks read, which the selection keeps in the SELECT for
        them even when the read itself asked for none of it."""
        return self._seen_by

    async def read(self, request: Request, query: QuerySet, ctx: dict[str, Any]) -> list[dict[str, Any]]:
        """The rows of ``query``, serialized and handed to the hooks."""
        reads, seen = await read_rows(query, self._map_fields, self._seen_by)

        for transformer in self._views_hooks:
            await transformer.get_views(request, seen, ctx)

        for index, item in enumerate(seen):
            for transformer in self._view_hooks:
                reads[index] = await transformer.get_view(request, item, reads[index], ctx)

        return reads


def plan_row_read[M: BaseModel | BaseView](
    model_cls: type[M],
    fields: str | None,
    transformers: list[BaseViewTransformer] | None = None,
    views: bool = True,
) -> RowRead | None:
    """How this read is answered by its rows, or None to build the models.

    ``views`` says whether :class:`GetViewsTransformer` runs for this action: a
    read of one record never calls it, and what it reads is then none of its
    business.
    """
    if not fields:
        return None

    vtr = get_service(ViewTransformerRegistry)
    view_hooks = vtr.get_transformers(GetViewTransformer, model_cls, transformers)
    views_hooks = vtr.get_transformers(GetViewsTransformer, model_cls, transformers) if views else []
    declared = [view_transformer_reads_of(hook, "get_view") for hook in view_hooks]
    declared += [view_transformer_reads_of(hook, "get_views") for hook in views_hooks]

    if any(names is None for names in declared):
        return None

    seen_by = frozenset(name for names in declared for name in names or ()) if declared else None

    if seen_by is not None and not can_read_paths(model_cls, seen_by):
        return None

    map_fields = parse_field_selector_input(model_cls, fields)

    if not map_fields or not can_read_rows(model_cls, map_fields):
        return None

    return RowRead(map_fields, seen_by, view_hooks, views_hooks)
