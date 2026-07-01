# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from fastedgy.dependencies import get_service, register_service

if TYPE_CHECKING:
    from fastedgy.orm.filter.types import Filter
    from fastedgy.orm.query import QuerySet


GlobalFilterGetter = Callable[[], "Filter | None"]
GlobalFilterApply = Callable[[type], bool] | None

_C = TypeVar("_C", bound=type)


@dataclass(frozen=True)
class GlobalFilter:
    get_filter: GlobalFilterGetter
    apply: GlobalFilterApply = None


class GlobalFilterRegistry:
    """Registry for model global filters applied to every managed queryset."""

    def __init__(self):
        self._filters: dict[type, list[GlobalFilter]] = {}

    def register(
        self,
        model_cls: type,
        get_filter: GlobalFilterGetter,
        apply: GlobalFilterApply = None,
    ) -> None:
        self._filters.setdefault(model_cls, []).append(GlobalFilter(get_filter, apply))

    def get_filters(self, model_cls: type) -> list[GlobalFilter]:
        filters: list[GlobalFilter] = []

        for klass in model_cls.__mro__:
            filters.extend(self._filters.get(klass, []))

        return filters

    def has_filters(self, model_cls: type) -> bool:
        return any(klass in self._filters for klass in model_cls.__mro__)


register_service(GlobalFilterRegistry)


def global_filter(
    get_filter: GlobalFilterGetter,
    apply: GlobalFilterApply = None,
) -> Callable[[_C], _C]:
    def decorator(cls: _C) -> _C:
        get_service(GlobalFilterRegistry).register(cls, get_filter, apply)
        return cls

    return decorator


def apply_global_filters(queryset: "QuerySet") -> "QuerySet":
    from fastedgy.orm.filter.builder import filter_query

    registry = get_service(GlobalFilterRegistry)
    model_class = queryset.model_class

    for gf in registry.get_filters(model_class):
        if gf.apply is not None and not gf.apply(model_class):
            continue

        filters = gf.get_filter()

        if filters is not None:
            queryset = filter_query(queryset, filters, allow_excluded=True)

    return queryset


__all__ = [
    "GlobalFilter",
    "GlobalFilterRegistry",
    "GlobalFilterGetter",
    "GlobalFilterApply",
    "global_filter",
    "apply_global_filters",
]
