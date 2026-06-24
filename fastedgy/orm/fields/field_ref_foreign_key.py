# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import RefForeignKey as _RefForeignKey

from .field_options import FieldOptions


class RefForeignKey(FieldOptions[Any], _RefForeignKey): ...


__all__ = [
    "RefForeignKey",
]
