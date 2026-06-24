# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import time

from edgy.core.db.fields import TimeField as _TimeField

from .field_options import FieldOptions


class TimeField(FieldOptions[time], _TimeField): ...


__all__ = [
    "TimeField",
]
