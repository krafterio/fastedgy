# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod

from typing import Any, TYPE_CHECKING
from pathlib import Path

from fastedgy.http import Request
from fastedgy.orm.query import QuerySet
from fastedgy.schemas.base import Pagination

from pydantic import BaseModel

if TYPE_CHECKING:
    from fastapi import UploadFile
    from fastedgy.models.base import BaseModel as EdgyBaseModel


class BaseViewTransformer(ABC):
    """Base class for all view transformers."""

    pass


class PrePaginateViewTransformer(BaseViewTransformer):
    @abstractmethod
    async def pre_paginate(
        self, request: Request, query: QuerySet, ctx: dict[str, Any]
    ) -> QuerySet: ...


class PostPaginateViewTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def post_paginate(
        self, request: Request, pagination: Pagination[M], ctx: dict[str, Any]
    ) -> None: ...


class PreLoadRecordViewTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def pre_load_record(
        self, request: Request, query: QuerySet, ctx: dict[str, Any]
    ) -> QuerySet: ...


class GetViewsTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def get_views(
        self, request: Request, items: list[M], ctx: dict[str, Any]
    ) -> None: ...


class GetViewTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def get_view(
        self, request: Request, item: M, item_dump: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]: ...


class PreSaveTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def pre_save(
        self, request: Request, item: M, item_data: BaseModel, ctx: dict[str, Any]
    ) -> None: ...


class PostSaveTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def post_save(
        self, request: Request, item: M, item_data: BaseModel, ctx: dict[str, Any]
    ) -> None: ...


class PreDeleteTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def pre_delete(
        self, request: Request, record: M, ctx: dict[str, Any]
    ) -> None: ...


class PostDeleteTransformer[M = BaseModel](BaseViewTransformer):
    @abstractmethod
    async def post_delete(
        self, request: Request, record: M, ctx: dict[str, Any]
    ) -> None: ...


class PreUploadTransformer(BaseViewTransformer):
    @abstractmethod
    async def pre_upload(
        self,
        request: Request,
        record: "EdgyBaseModel",
        field: str,
        file: "UploadFile",
        ctx: dict[str, Any],
    ) -> bool:
        """
        Pre-upload transformer.

        Returns:
            bool: Whether to use global storage (True) or workspace storage (False)
        """
        ...


class PostUploadTransformer(BaseViewTransformer):
    @abstractmethod
    async def post_upload(
        self,
        request: Request,
        record: "EdgyBaseModel",
        field: str,
        path: str,
        ctx: dict[str, Any],
    ) -> str: ...


class PreDownloadTransformer(BaseViewTransformer):
    @abstractmethod
    async def pre_download(
        self,
        request: Request,
        path: str,
        ctx: dict[str, Any],
    ) -> bool:
        """
        Pre-download transformer.

        Returns:
            bool: Whether to use global storage (True) or workspace storage (False)
        """
        ...


class PostDownloadTransformer(BaseViewTransformer):
    @abstractmethod
    async def post_download(
        self,
        request: Request,
        path: str,
        served_path: Path,
        ctx: dict[str, Any],
    ) -> Path: ...


__all__ = [
    "BaseViewTransformer",
    "PrePaginateViewTransformer",
    "PostPaginateViewTransformer",
    "GetViewsTransformer",
    "GetViewTransformer",
    "PreSaveTransformer",
    "PostSaveTransformer",
    "PreDeleteTransformer",
    "PostDeleteTransformer",
    "PreUploadTransformer",
    "PostUploadTransformer",
    "PreDownloadTransformer",
    "PostDownloadTransformer",
]
