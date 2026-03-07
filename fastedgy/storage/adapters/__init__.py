# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.storage.adapters.base import StorageAdapter
from fastedgy.storage.adapters.filesystem import FilesystemAdapter
from fastedgy.storage.adapters.s3 import S3Adapter

__all__ = [
    "StorageAdapter",
    "FilesystemAdapter",
    "S3Adapter",
]
