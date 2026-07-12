# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.storage.services import Storage
from fastedgy.storage.models import AttachmentMixin, AttachmentType
from fastedgy.storage.adapters import StorageAdapter, FilesystemAdapter, S3Adapter
from fastedgy.storage.routing import is_global_storage_model, is_global_storage_path

__all__ = [
    "Storage",
    "StorageAdapter",
    "FilesystemAdapter",
    "S3Adapter",
    "AttachmentMixin",
    "AttachmentType",
    "is_global_storage_model",
    "is_global_storage_path",
]
