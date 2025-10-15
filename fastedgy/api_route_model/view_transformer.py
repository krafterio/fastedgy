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


class PreExportTransformer(BaseViewTransformer):
    @abstractmethod
    async def pre_export(
        self, request: Request, query: QuerySet, ctx: dict[str, Any]
    ) -> QuerySet:
        """
        Pre-export transformer.

        Called before exporting items. Can modify the query.

        Args:
            request: The HTTP request
            query: The QuerySet to export
            ctx: Context dictionary for sharing data

        Returns:
            Modified QuerySet
        """
        ...


class PostExportTransformer(BaseViewTransformer):
    @abstractmethod
    async def post_export(
        self,
        request: Request,
        file_content: bytes,
        filename: str,
        ctx: dict[str, Any],
    ) -> tuple[bytes, str]:
        """
        Post-export transformer.

        Called after generating the export file. Can modify content or filename.

        Args:
            request: The HTTP request
            file_content: The generated file content
            filename: The generated filename
            ctx: Context dictionary for sharing data

        Returns:
            Tuple of (modified_content, modified_filename)
        """
        ...


class PreImportTransformer(BaseViewTransformer):
    @abstractmethod
    async def pre_import(
        self,
        request: Request,
        file: "UploadFile",
        ctx: dict[str, Any],
    ) -> "UploadFile":
        """
        Pre-import transformer.

        Called before importing items. Can validate or pre-process the file.

        Args:
            request: The HTTP request
            file: The uploaded file
            ctx: Context dictionary for sharing data

        Returns:
            The file (possibly modified)
        """
        ...


class PostImportTransformer(BaseViewTransformer):
    @abstractmethod
    async def post_import(
        self,
        request: Request,
        result: Any,
        ctx: dict[str, Any],
    ) -> None:
        """
        Post-import transformer.

        Called after importing items (on success).

        Args:
            request: The HTTP request
            result: The ImportResult
            ctx: Context dictionary for sharing data
        """
        ...


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
    "PreExportTransformer",
    "PostExportTransformer",
    "PreImportTransformer",
    "PostImportTransformer",
]
