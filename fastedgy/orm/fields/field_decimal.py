# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from decimal import Decimal

from edgy.core.db.fields import DecimalField as _DecimalField

from .field_options import FieldOptions


class DecimalField(FieldOptions[Decimal], _DecimalField): ...


__all__ = [
    "DecimalField",
]
