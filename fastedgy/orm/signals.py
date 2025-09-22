# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.signals import (
    pre_save,
    pre_update,
    post_update,
    pre_delete,
    post_delete,
)


__all__ = [
    "pre_save",
    "pre_update",
    "post_update",
    "pre_delete",
    "post_delete",
]
