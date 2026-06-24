# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import TextField as _TextField

from .field_options import FieldOptions


class TextField(FieldOptions[str], _TextField): ...


__all__ = [
    "TextField",
]
