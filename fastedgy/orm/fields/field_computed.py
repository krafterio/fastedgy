# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import ComputedField as _ComputedField


class ComputedField(_ComputedField):
    """A value the getter derives rather than a column the row carries.

    Mark the getter with `@computed_field_deps(...)` to name what it reads: a
    read that selects this field then loads exactly those columns.

    Unmarked, such a read cannot prune any column of the model. The field names
    no column of its own, so deferring the ones the getter turns out to need
    sends every instance back to the database for its own row, which is the
    difference between one query and one per row.
    """

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        return super().__new__(cls)


__all__ = [
    "ComputedField",
]
