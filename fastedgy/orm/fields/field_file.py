# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import FileField as _FileField

from .field_options import FieldOptions


class FileField(FieldOptions[Any], _FileField): ...


__all__ = [
    "FileField",
]
