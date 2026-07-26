# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any


def is_copyable_field(field: Any) -> bool:
    """Whether a record's copy carries this field over.

    Fields say it themselves with ``copy=True`` / ``copy=False``. Left unsaid,
    everything a record owns is copyable except what identifies or dates that
    particular row: a primary key, a ``read_only`` field (a timestamp, a
    server-generated reference), and the virtual fields Edgy installs for
    relations and derived values (``no_copy``).
    """
    declared = getattr(field, "copy", None)

    if declared is not None:
        return bool(declared)

    if getattr(field, "primary_key", False) or getattr(field, "read_only", False):
        return False

    return not getattr(field, "no_copy", False)


def is_copyable_to_many_field(field: Any) -> bool:
    """Whether a copy re-creates this to-many field's links once it exists."""
    return bool(getattr(field, "is_m2m", False)) and is_copyable_field(field)


__all__ = [
    "is_copyable_field",
    "is_copyable_to_many_field",
]
