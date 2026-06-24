# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import EmailField as _EmailField

from .field_options import FieldOptions


class EmailField(FieldOptions[str], _EmailField): ...


__all__ = [
    "EmailField",
]
