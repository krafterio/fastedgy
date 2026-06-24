# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import IntegerField as _IntegerField

from .field_options import FieldOptions


class IntegerField(FieldOptions[int], _IntegerField): ...


__all__ = [
    "IntegerField",
]
