# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import URLField as _URLField

from .field_options import FieldOptions


class URLField(FieldOptions[str], _URLField): ...


__all__ = [
    "URLField",
]
