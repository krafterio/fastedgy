# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import ExcludeField as _ExcludeField

from .field_options import FieldOptions


class ExcludeField(FieldOptions[Any], _ExcludeField): ...


__all__ = [
    "ExcludeField",
]
