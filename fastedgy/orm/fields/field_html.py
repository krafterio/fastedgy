# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import TextField

from .field_options import FieldOptions
from .field_translatable import TranslatableOptions


class HTMLField(FieldOptions[str], TranslatableOptions, TextField): ...


__all__ = [
    "HTMLField",
]
