# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from functools import cache
from typing import Any

from .field_char import CharField


class FileField(CharField):
    """A stored file: its storage path in the column of a CharField. The storage routes write it, and the API
    stores a data URL written to it.

    Its field class derives from the one of CharField, so the column, the filter operators and the type exposed to
    the clients stay those of a CharField."""

    @staticmethod
    @cache
    def _get_field_cls(factory_cls: Any) -> Any:
        parent = factory_cls.__mro__[1]

        return type(factory_cls.__name__, (parent._get_field_cls(parent),), {})


__all__ = [
    "FileField",
]
