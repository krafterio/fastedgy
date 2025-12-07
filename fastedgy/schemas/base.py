# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, TypeVar
from datetime import datetime

from pydantic import BaseModel as PydanticBaseModel, computed_field, field_serializer


class BaseModel(PydanticBaseModel):
    """
    Base Pydantic schema with timezone-aware datetime serialization.

    All datetime fields will be serialized with the timezone from the current
    request context, ensuring legacy app compatibility.

    Example:
        ```python
        from fastedgy.schemas.base import BaseModel

        class UserCreate(BaseModel):
            email: str
            created_at: datetime
        ```

    This will serialize datetime with timezone:
        {"email": "user@example.com", "created_at": "2025-10-04T19:00:00+02:00"}

    Instead of UTC:
        {"email": "user@example.com", "created_at": "2025-10-04T17:00:00Z"}
    """

    @field_serializer("*", mode="wrap", when_used="json")
    @classmethod
    def _serialize_datetime_fields(cls, value, handler, info):
        """Serialize all datetime fields with timezone from context."""
        result = handler(value)

        if isinstance(value, datetime):
            from fastedgy.serializers import datetime_serializer

            return datetime_serializer(value)

        return result


M = TypeVar("M", bound=BaseModel)


class Pagination[M = Any](BaseModel):
    """
    Generic schema for paginated list responses.

    This schema provides a standardized structure for API endpoints that return
    paginated lists of items. It includes the actual items along with
    pagination metadata.

    Type Parameters:
        M: The type of items in the list (defaults to BaseModel).

    Attributes:
        items (list[M]): The list of items for the current page.
        total (int): Total number of items across all pages.
        limit (int): Number of items per page.
        offset (int): Index of the first item in the current page.
    """

    items: list[M]
    total: int
    limit: int
    offset: int

    @computed_field
    @property
    def total_pages(self) -> int:
        return (self.total + self.limit - 1) // self.limit


class List[M = Any](Pagination[M]):
    pass


class SimpleMessage(BaseModel):
    message: str


__all__ = [
    "BaseModel",
    "Pagination",
    "List",
    "SimpleMessage",
]
