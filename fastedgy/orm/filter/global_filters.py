# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import inspect

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from fastedgy.dependencies import get_service, register_service

if TYPE_CHECKING:
    from fastedgy.orm.filter.types import Filter
    from fastedgy.orm.query import QuerySet


GlobalFilterGetter = Callable[[], "Filter | None"] | Callable[[type], "Filter | None"]
GlobalFilterApply = Callable[[type], bool] | None

_C = TypeVar("_C", bound=type)


@dataclass(frozen=True)
class GlobalFilter:
    get_filter: GlobalFilterGetter
    apply: GlobalFilterApply = None
    takes_model: bool = False


def _getter_takes_model(get_filter: GlobalFilterGetter) -> bool:
    """A getter may declare a single positional parameter to receive the queried
    model class (needed by filters whose shape depends on the model, e.g. the
    workspace-shareable confinement paths). Zero-argument getters keep the
    historical contract."""
    try:
        return len(inspect.signature(get_filter).parameters) >= 1
    except (TypeError, ValueError):
        return False


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
        self._filters.setdefault(model_cls, []).append(GlobalFilter(get_filter, apply, _getter_takes_model(get_filter)))

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

        filters = gf.get_filter(model_class) if gf.takes_model else gf.get_filter()  # type: ignore[call-arg]

        if filters is not None:
            queryset = filter_query(queryset, filters, allow_excluded=True)

    return queryset


def _reference_pk(value: Any) -> Any:
    from fastedgy.orm.fields import BaseFieldType

    # An unset foreign key on a fresh instance resolves to its class-level field
    # descriptor (a BaseFieldType), not a value — nothing to validate there.
    if value is None or isinstance(value, BaseFieldType):
        return None

    return getattr(value, "pk", value)


async def validate_write_references(instance: Any) -> None:
    from fastedgy import context

    if context.get_user() is None:
        return

    from fastedgy.orm.fields import ForeignKey

    registry = get_service(GlobalFilterRegistry)
    model_cls = type(instance)

    targets = {
        name: field.target
        for name, field in model_cls.meta.fields.items()
        if isinstance(field, ForeignKey)
        and isinstance(getattr(field, "target", None), type)
        and registry.has_filters(field.target)
    }

    if not targets:
        return

    previous = None

    if getattr(instance, "_db_loaded", False) and instance.pk is not None:
        previous = await model_cls.global_query.filter(pk=instance.pk).first()

    for name, target in targets.items():
        pk = _reference_pk(getattr(instance, name, None))

        if pk is None:
            continue

        if previous is not None and _reference_pk(getattr(previous, name, None)) == pk:
            continue

        if not await target.query.filter(pk=pk).exists():
            from fastapi import HTTPException
            from fastedgy.i18n import _t

            raise HTTPException(
                status_code=403,
                detail=_t("You do not have access to the referenced resource."),
            )


__all__ = [
    "GlobalFilter",
    "GlobalFilterRegistry",
    "GlobalFilterGetter",
    "GlobalFilterApply",
    "global_filter",
    "apply_global_filters",
    "validate_write_references",
]
