# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import OneToOneField as _OneToOneField

from .field_options import FieldOptions


class OneToOneField(FieldOptions[Any], _OneToOneField): ...


OneToOne = OneToOneField


__all__ = [
    "OneToOne",
    "OneToOneField",
]
