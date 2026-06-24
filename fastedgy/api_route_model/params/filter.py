# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastapi.params import Query, Header


def FilterQuery() -> Any:
    return Query(
        default=None,
        title="Filter",
        description="Filter the list of items with the filter expression build with rules and conditions",
    )


def FilterHeader() -> Any:
    return Header(
        default=None,
        title="Filter",
        description="Filter the list of items with the filter expression build with rules and conditions",
        alias="X-Filter",
    )


__all__ = [
    "FilterQuery",
    "FilterHeader",
]
