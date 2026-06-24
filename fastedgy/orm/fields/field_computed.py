# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import ComputedField as _ComputedField


class ComputedField(_ComputedField):
    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        return super().__new__(cls)


__all__ = [
    "ComputedField",
]
