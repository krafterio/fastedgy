# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import TextField

from .field_options import FieldOptions


class HTMLField(FieldOptions[str], TextField): ...


__all__ = [
    "HTMLField",
]
