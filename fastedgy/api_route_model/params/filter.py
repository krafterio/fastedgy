# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi.params import Query, Header


class FilterQuery(Query):
    def __init__(self):
        super().__init__(
            default=None,
            title="Filter",
            description="Filter the list of items with the filter expression build with rules and conditions",
        )


class FilterHeader(Header):
    def __init__(self):
        super().__init__(
            default=None,
            title="Filter",
            description="Filter the list of items with the filter expression build with rules and conditions",
            alias="X-Filter",
        )


__all__ = [
    "FilterQuery",
    "FilterHeader",
]
