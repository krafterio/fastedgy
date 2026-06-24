# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import CharField

from .field_options import FieldOptions


class PhoneField(FieldOptions[str], CharField): ...


__all__ = [
    "PhoneField",
]
