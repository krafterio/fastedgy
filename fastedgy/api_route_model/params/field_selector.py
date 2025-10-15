# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi.params import Query, Header


class FieldSelectorQuery(Query):
    """FastAPI Query parameter for field selection."""

    def __init__(self):
        super().__init__(
            default=None,
            title="Fields Selector",
            description="Select which fields to include in the response and use dot notation to select nested fields (ex. 'name,company.name')",
        )


class FieldSelectorHeader(Header):
    """FastAPI Header parameter for field selection."""

    def __init__(self):
        super().__init__(
            default=None,
            title="Fields Selector",
            description="Select which fields to include in the response and use dot notation to select nested fields (ex. 'name,company.name')",
            alias="X-Fields",
        )


__all__ = [
    "FieldSelectorQuery",
    "FieldSelectorHeader",
]
