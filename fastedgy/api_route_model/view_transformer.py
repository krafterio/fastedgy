# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod

from typing import Any

from fastedgy.orm.query import QuerySet
from fastedgy.schemas.base import Pagination

from pydantic import BaseModel

from starlette.requests import Request


class BaseViewTransformer(ABC):
    """Base class for all view transformers."""
    pass


class PrePaginateViewTransformer(BaseViewTransformer):
    @abstractmethod
    async def pre_paginate(self, request: Request, query: QuerySet, ctx: dict[str, Any]) -> QuerySet:...


class PostPaginateViewTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def post_paginate(self, request: Request, pagination: Pagination[M], ctx: dict[str, Any]) -> None:...


class GetViewsTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def get_views(self, request: Request, items: list[M], ctx: dict[str, Any]) -> None:...


class GetViewTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def get_view(self, request: Request, item: M, item_dump: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:...


class PreSaveTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def pre_save(self, request: Request, item: M, item_data: BaseModel, ctx: dict[str, Any]) -> None:...


class PostSaveTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def post_save(self, request: Request, item: M, item_data: BaseModel, ctx: dict[str, Any]) -> None:...


__all__ = [
    "BaseViewTransformer",
    "PrePaginateViewTransformer",
    "PostPaginateViewTransformer",
    "GetViewsTransformer",
    "GetViewTransformer",
    "PreSaveTransformer",
    "PostSaveTransformer",
]
