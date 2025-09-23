# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.storage.models.attachment import (
    AttachmentMixin,
    AttachmentPathMixin,
    AttachmentType,
)


class BaseAttachment(AttachmentMixin):
    class Meta:  # type: ignore
        abstract = True


__all__ = [
    "BaseAttachment",
    "AttachmentPathMixin",
    "AttachmentType",
]
