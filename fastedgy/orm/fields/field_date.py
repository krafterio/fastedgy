# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import date

from edgy.core.db.fields import DateField as _DateField

from .field_options import FieldOptions


class DateField(FieldOptions[date], _DateField): ...


__all__ = [
    "DateField",
]
