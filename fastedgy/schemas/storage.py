# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any
from pydantic import BaseModel


class UploadedAttachments[T: Any](BaseModel):
    attachments: list[T]


__all__ = [
    "UploadedAttachments",
]
