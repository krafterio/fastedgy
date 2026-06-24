# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import FloatField as _FloatField

from .field_options import FieldOptions


class FloatField(FieldOptions[float], _FloatField): ...


__all__ = [
    "FloatField",
]
