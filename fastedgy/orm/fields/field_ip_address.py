# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import IPAddressField as _IPAddressField

from .field_options import FieldOptions


class IPAddressField(FieldOptions[str], _IPAddressField): ...


__all__ = [
    "IPAddressField",
]
