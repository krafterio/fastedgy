# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.signals import (
    pre_save,
    post_save,
    pre_update,
    post_update,
    pre_delete,
    post_delete,
)

from .fulltext import register_fulltext_signals, register_all_fulltext_signals


__all__ = [
    "pre_save",
    "post_save",
    "pre_update",
    "post_update",
    "pre_delete",
    "post_delete",
    "register_fulltext_signals",
    "register_all_fulltext_signals",
]
