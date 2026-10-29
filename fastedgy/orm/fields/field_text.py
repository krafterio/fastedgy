# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import TextField as _TextField

from .field_options import FieldOptions
from .field_translatable import TranslatableOptions


class TextField(FieldOptions[str], TranslatableOptions, _TextField): ...


__all__ = [
    "TextField",
]
