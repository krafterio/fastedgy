# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import ManyToManyField as _ManyToManyField

from .field_options import FieldOptions


class ManyToManyField(FieldOptions[Any], _ManyToManyField): ...


ManyToMany = ManyToManyField


__all__ = [
    "ManyToMany",
    "ManyToManyField",
]
