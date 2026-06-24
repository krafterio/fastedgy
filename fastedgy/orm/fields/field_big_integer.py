# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import BigIntegerField as _BigIntegerField

from .field_options import FieldOptions


class BigIntegerField(FieldOptions[int], _BigIntegerField): ...


__all__ = [
    "BigIntegerField",
]
