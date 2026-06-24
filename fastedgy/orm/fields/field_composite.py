# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import CompositeField as _CompositeField

from .field_options import FieldOptions


class CompositeField(FieldOptions[Any], _CompositeField): ...


__all__ = [
    "CompositeField",
]
