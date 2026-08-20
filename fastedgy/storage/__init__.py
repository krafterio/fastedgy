# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.storage.adapters import FilesystemAdapter, S3Adapter, StorageAdapter
from fastedgy.storage.models import AttachmentMixin, AttachmentType
from fastedgy.storage.routing import (
    is_global_storage_model,
    is_global_storage_path,
    resolve_workspace_for_path,
)
from fastedgy.storage.services import Storage

__all__ = [
    "AttachmentMixin",
    "AttachmentType",
    "FilesystemAdapter",
    "S3Adapter",
    "Storage",
    "StorageAdapter",
    "is_global_storage_model",
    "is_global_storage_path",
    "resolve_workspace_for_path",
]
