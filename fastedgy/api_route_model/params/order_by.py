# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastapi.params import Query, Header


def OrderByQuery() -> Any:
    return Query(
        default=None,
        title="Order by",
        description="Order the list of items by field(s) separated by commas (ex. 'created_at:desc,name:asc')",
    )


def OrderByHeader() -> Any:
    return Header(
        default=None,
        title="Order by",
        description="Order the list of items by field(s) separated by commas (ex. 'created_at:desc,name:asc')",
        alias="X-Order-By",
    )


__all__ = [
    "OrderByQuery",
    "OrderByHeader",
]
