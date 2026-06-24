# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastapi.params import Query, Header


def FieldSelectorQuery() -> Any:
    """FastAPI Query parameter for field selection."""
    return Query(
        default=None,
        title="Fields Selector",
        description="Select which fields to include in the response and use dot notation to select nested fields (ex. 'name,company.name')",
    )


def FieldSelectorHeader() -> Any:
    """FastAPI Header parameter for field selection."""
    return Header(
        default=None,
        title="Fields Selector",
        description="Select which fields to include in the response and use dot notation to select nested fields (ex. 'name,company.name')",
        alias="X-Fields",
    )


__all__ = [
    "FieldSelectorQuery",
    "FieldSelectorHeader",
]
