# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Generic, TypeVar

from fastedgy.schemas import BaseModel


class UploadedAttachment(BaseModel):
    name: str
    extension: str
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


T = TypeVar("T", bound=UploadedAttachment)


class UploadedAttachments(BaseModel, Generic[T]):
    attachments: list[T]


class UploadedModelField(BaseModel):
    path: str


__all__ = [
    "UploadedAttachments",
    "UploadedAttachment",
]
