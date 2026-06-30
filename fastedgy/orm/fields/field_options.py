# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from functools import lru_cache
from typing import Any, Literal, overload

from edgy.core.db.fields.factories import (
    FieldFactory,
    FieldFactoryMeta,
    ForeignKeyFieldFactory,
)
from pydantic_core import PydanticUndefined

from ...i18n import TranslatableString


_FACTORY_ROOTS = frozenset({FieldFactory, ForeignKeyFieldFactory})


def _resolve_default_conflict(field: Any) -> None:
    """Ensure a built field never carries both ``default`` and ``default_factory``.

    Pydantic forbids a ``FieldInfo`` holding both, and FastAPI (>= 0.123.7)
    enforces it: it rebuilds every model field as
    ``Field(**asdict(field_info)["attributes"])`` while flattening models for the
    OpenAPI schema, raising ``TypeError: cannot specify both default and
    default_factory`` otherwise. Two FastEdgy patterns produce the conflict:

    - ``auto_now`` / ``auto_now_add`` datetime/date fields: Edgy injects an
      authoritative, timezone-aware ``default = partial(now)``; a redundant
      explicit ``default_factory`` is dropped.
    - any other field declared with an explicit ``default_factory``: Edgy stores
      a spurious literal ``default`` (``None``) alongside it, so the literal
      default is cleared and the factory stands alone.
    """
    default = getattr(field, "default", PydanticUndefined)
    factory = getattr(field, "default_factory", None)

    if default is PydanticUndefined or factory is None:
        return

    if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
        field.default_factory = None
    else:
        field.default = PydanticUndefined


class FieldOptions[T = Any]:
    """Mixin typing an Edgy field factory by its declared value type.

    Edgy field factories annotate ``__new__`` as returning ``BaseFieldType``,
    which makes ``name: str = fields.CharField(...)`` fail static type checks.
    This mixin overrides ``__new__`` to return the field value type ``T`` (or
    ``T | None`` when ``null=True``), and exposes the extra FastEdgy options
    (``label``, ``searchable``, ``sortable``) shared by every field.

    ``_get_field_cls`` is delegated to the wrapped Edgy factory so the produced
    field class keeps Edgy's identity: ``isinstance(field, edgy.CharField)`` and
    ``isinstance(field, fastedgy.CharField)`` both stay true.
    """

    @staticmethod
    @lru_cache(maxsize=None)
    def _get_field_cls(factory_cls: Any) -> Any:
        if "__new__" not in factory_cls.__dict__:
            for base in factory_cls.__mro__:
                if (
                    base is not factory_cls
                    and base not in _FACTORY_ROOTS
                    and isinstance(base, FieldFactoryMeta)
                    and base.__module__.startswith("edgy")
                    and base.__name__ == factory_cls.__name__
                ):
                    return FieldFactory._get_field_cls(base)

        return FieldFactory._get_field_cls(factory_cls)

    @overload
    def __new__(
        cls,
        *args: Any,
        null: Literal[True],
        label: TranslatableString | str | None = None,
        searchable: bool | str | None = None,
        sortable: bool | None = None,
        **kwargs: Any,
    ) -> T | None: ...

    @overload
    def __new__(
        cls,
        *args: Any,
        null: Literal[False] = False,
        label: TranslatableString | str | None = None,
        searchable: bool | str | None = None,
        sortable: bool | None = None,
        **kwargs: Any,
    ) -> T: ...

    def __new__(
        cls,
        *args: Any,
        label: TranslatableString | str | None = None,
        searchable: bool | str | None = None,
        sortable: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        if label is not None:
            kwargs["label"] = label

        if searchable is not None:
            kwargs["searchable"] = searchable

        if sortable is not None:
            kwargs["sortable"] = sortable

        field = super().__new__(cls, *args, **kwargs)
        _resolve_default_conflict(field)

        return field


__all__ = [
    "FieldOptions",
]
