# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import PasswordField as _PasswordField

from .field_options import FieldOptions


class PasswordField(FieldOptions[str], _PasswordField): ...


__all__ = [
    "PasswordField",
]
