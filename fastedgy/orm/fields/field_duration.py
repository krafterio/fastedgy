# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import timedelta

from edgy.core.db.fields import DurationField as _DurationField

from .field_options import FieldOptions


class DurationField(FieldOptions[timedelta], _DurationField): ...


__all__ = [
    "DurationField",
]
