# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pydantic import BaseModel


class UploadedAttachment(BaseModel):
    name: str
    extension: str
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


class UploadedAttachments[T: UploadedAttachment](BaseModel):
    attachments: list[T]


class UploadedModelField(BaseModel):
    path: str


__all__ = [
    "UploadedAttachments",
    "UploadedAttachment",
]
