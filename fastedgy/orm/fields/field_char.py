# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import CharField as _CharField

from .field_options import FieldOptions
from .field_translatable import TranslatableOptions


class CharField(FieldOptions[str], TranslatableOptions, _CharField): ...


__all__ = [
    "CharField",
]
