# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi.params import Query, Header


class OrderByQuery(Query):
    def __init__(self):
        super().__init__(
            default=None,
            title="Order by",
            description="Order the list of items by field(s) separated by commas (ex. 'created_at:desc,name:asc')",
        )


class OrderByHeader(Header):
    def __init__(self):
        super().__init__(
            default=None,
            title="Order by",
            description="Order the list of items by field(s) separated by commas (ex. 'created_at:desc,name:asc')",
            alias="X-Order-By",
        )


__all__ = [
    "OrderByQuery",
    "OrderByHeader",
]
