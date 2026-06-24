# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import PlaceholderField as _PlaceholderField

from .field_options import FieldOptions


class PlaceholderField(FieldOptions[Any], _PlaceholderField): ...


__all__ = [
    "PlaceholderField",
]
