# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import BinaryField as _BinaryField

from .field_options import FieldOptions


class BinaryField(FieldOptions[bytes], _BinaryField): ...


__all__ = [
    "BinaryField",
]
