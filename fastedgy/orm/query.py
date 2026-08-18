# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.querysets import (
    QuerySet,
    Q,
    and_,
    not_,
    or_,
    Prefetch,
)


class OrderingQuerySet(QuerySet):
    """Adds ordering by a path that fans out (reverse one-to-many, many-to-many).

    The ORM resolves every ordering term to a join, which for such a path
    repeats the record once per related row: the page comes back short and
    ``count()`` counts join rows. These terms are kept out of the join crawler
    and compiled to a correlated aggregate instead, in `_prepare_order_by`.
    """

    def order_by(self, *order_by: str) -> QuerySet:
        aggregated = tuple(term for term in order_by if self._orders_on_aggregate(term))

        if not aggregated:
            return super().order_by(*order_by)

        queryset = super().order_by(*(term for term in order_by if term not in aggregated))
        # The terms stay in the ordering, they just never reach the crawler that
        # would join them; `_prepare_order_by` compiles them at build time.
        queryset._order_by = order_by

        return queryset

    def _prepare_order_by(self, order_by: str, tables_and_models: Any) -> Any:
        column = self._rank_column(order_by)

        if column is None:
            column = self._aggregate_column(order_by, order_by.startswith("-"))

        if column is None:
            return super()._prepare_order_by(order_by, tables_and_models)

        return column.desc() if order_by.startswith("-") else column

    def _rank_column(self, order_by: str) -> Any | None:
        """The relevance of a fulltext search, ranked by the label the filter added."""
        label = f"_{order_path(order_by)}_rank"

        return next((extra for extra in (self._extra_select or ()) if getattr(extra, "name", None) == label), None)

    def _aggregate_column(self, term: str, descending: bool) -> Any | None:
        from fastedgy.orm.order_by import aggregated_relation_column

        if not self._orders_on_aggregate(term):
            return None

        return aggregated_relation_column(self.model_class, order_path(term), descending)

    def _orders_on_aggregate(self, order_by: str) -> bool:
        from fastedgy.orm.filter.utils import has_duplicating_relation_path

        # A filter keeps its join when several of its rules share one relation,
        # and dedupes with DISTINCT ON (pk). PostgreSQL wants those expressions
        # to lead the ORDER BY, so the aggregate cannot: that query keeps the
        # join-based ordering. A single rule per relation compiles to EXISTS,
        # leaves no DISTINCT ON behind, and takes the aggregate.
        if self.distinct_on:
            return False

        return has_duplicating_relation_path(self.model_class, order_path(order_by))


def order_path(order_by: str) -> str:
    """The dotted field path an ordering term names, without its direction."""
    return order_by.lstrip("-").replace("__", ".")


__all__ = [
    "QuerySet",
    "OrderingQuerySet",
    "order_path",
    "Q",
    "and_",
    "not_",
    "or_",
    "Prefetch",
]
