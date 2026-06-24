# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from functools import lru_cache
from typing import Any, Literal, overload

from edgy.core.db.fields.factories import (
    FieldFactory,
    FieldFactoryMeta,
    ForeignKeyFieldFactory,
)

from ...i18n import TranslatableString


_FACTORY_ROOTS = frozenset({FieldFactory, ForeignKeyFieldFactory})


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

        return super().__new__(cls, *args, **kwargs)


__all__ = [
    "FieldOptions",
]
