# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime

from edgy.core.db.fields import DateTimeField as _DateTimeField

from .field_options import FieldOptions


class DateTimeField(FieldOptions[datetime], _DateTimeField): ...


__all__ = [
    "DateTimeField",
]
