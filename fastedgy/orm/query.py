# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Any, Self, cast

from edgy.core.db.querysets import (
    Prefetch,
    Q,
    and_,
    not_,
    or_,
)
from edgy.core.db.querysets import (
    QuerySet as BaseQuerySet,
)


class QuerySet(BaseQuerySet):
    """The queryset every FastEdgy manager hands out.

    `filter()` takes the query-builder rules directly: `R`, `And` and `Or` route
    through `filter_query`, which validates the field and the operator, resolves
    relation paths and dedupes the joins a to-many rule would otherwise repeat.
    Everything else falls through to the ORM, so SQLAlchemy clauses and keyword
    lookups keep working unchanged.

    `order_by()` also accepts a path that fans out (reverse one-to-many,
    many-to-many). The ORM resolves every ordering term to a join, which for
    such a path repeats the record once per related row: the page comes back
    short and `count()` counts join rows. Those terms are kept out of the join
    crawler and compiled to a correlated aggregate instead.
    """

    if TYPE_CHECKING:
        # Edgy annotates every chaining method with its own base queryset,
        # which drops this type from the chain and makes the next `filter()`
        # look like the ORM's. They all clone `self`, so `Self` is the honest
        # annotation; these are declarations only, the ORM keeps the bodies.
        def and_(self, *args: Any, **kwargs: Any) -> Self: ...
        def batch_size(self, *args: Any, **kwargs: Any) -> Self: ...
        def defer(self, *args: Any, **kwargs: Any) -> Self: ...
        def distinct(self, *args: Any, **kwargs: Any) -> Self: ...
        def exclude(self, *args: Any, **kwargs: Any) -> Self: ...
        def exclude_secrets(self, *args: Any, **kwargs: Any) -> Self: ...
        def extra_select(self, *args: Any, **kwargs: Any) -> Self: ...
        def group_by(self, *args: Any, **kwargs: Any) -> Self: ...
        def limit(self, *args: Any, **kwargs: Any) -> Self: ...
        def local_or(self, *args: Any, **kwargs: Any) -> Self: ...
        def lookup(self, *args: Any, **kwargs: Any) -> Self: ...
        def not_(self, *args: Any, **kwargs: Any) -> Self: ...
        def offset(self, *args: Any, **kwargs: Any) -> Self: ...
        def only(self, *args: Any, **kwargs: Any) -> Self: ...
        def or_(self, *args: Any, **kwargs: Any) -> Self: ...
        def prefetch_related(self, *args: Any, **kwargs: Any) -> Self: ...
        def reference_select(self, *args: Any, **kwargs: Any) -> Self: ...
        def reverse(self, *args: Any, **kwargs: Any) -> Self: ...
        def select_for_update(self, *args: Any, **kwargs: Any) -> Self: ...
        def select_related(self, *args: Any, **kwargs: Any) -> Self: ...
        def using(self, *args: Any, **kwargs: Any) -> Self: ...
        def using_with_db(self, *args: Any, **kwargs: Any) -> Self: ...
        def where(self, *args: Any, **kwargs: Any) -> Self: ...

    filter_allow_excluded: bool = False
    """Whether `filter()` reaches fields the API hides (`exclude=True`).

    False on the scoped managers, so a rule built from request input cannot
    name a field the model keeps off its API surface. `global_query` sets it
    True: that manager already answers for the system, and the internal
    columns are exactly what a scheduler or a service filters on."""

    def filter(self, *clauses: Any, allow_excluded: bool | None = None, **kwargs: Any) -> QuerySet:
        # Deferred: the filter builder imports this module.
        from fastedgy.orm.filter import FilterCondition, FilterRule, filter_query

        rules = [clause for clause in clauses if isinstance(clause, FilterRule | FilterCondition)]

        if not rules:
            # Edgy types every chaining method as its own base queryset while it
            # really clones `self`, so the rule-aware type survives the chain.
            return cast(QuerySet, super().filter(*clauses, **kwargs))

        others = tuple(clause for clause in clauses if not isinstance(clause, FilterRule | FilterCondition))
        queryset = cast(QuerySet, super().filter(*others, **kwargs)) if others or kwargs else self

        excluded = self.filter_allow_excluded if allow_excluded is None else allow_excluded

        for rule in rules:
            queryset = filter_query(queryset, rule, allow_excluded=excluded)

        return cast(QuerySet, queryset)

    def order_by(self, *order_by: str) -> QuerySet:
        aggregated = tuple(term for term in order_by if self._orders_on_aggregate(term))

        if not aggregated:
            return cast(QuerySet, super().order_by(*order_by))

        queryset = super().order_by(*(term for term in order_by if term not in aggregated))
        # The terms stay in the ordering, they just never reach the crawler that
        # would join them; `_prepare_order_by` compiles them at build time.
        queryset._order_by = order_by

        return cast(QuerySet, queryset)

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
    "BaseQuerySet",
    "Prefetch",
    "Q",
    "QuerySet",
    "and_",
    "not_",
    "or_",
    "order_path",
]
