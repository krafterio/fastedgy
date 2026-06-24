# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import ImageField as _ImageField

from .field_options import FieldOptions


class ImageField(FieldOptions[Any], _ImageField): ...


__all__ = [
    "ImageField",
]
