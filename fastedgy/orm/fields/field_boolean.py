# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import BooleanField as _BooleanField

from .field_options import FieldOptions


class BooleanField(FieldOptions[bool], _BooleanField): ...


__all__ = [
    "BooleanField",
]
