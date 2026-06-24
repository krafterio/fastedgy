# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import SmallIntegerField as _SmallIntegerField

from .field_options import FieldOptions


class SmallIntegerField(FieldOptions[int], _SmallIntegerField): ...


__all__ = [
    "SmallIntegerField",
]
