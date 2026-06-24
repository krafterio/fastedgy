# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.attachment import AttachmentPathMixin
from fastedgy.api_route_model import api_route_model


@api_route_model()
class Attachment(AttachmentPathMixin):
    class Meta(AttachmentPathMixin.Meta):
        tablename = "attachments"


__all__ = [
    "Attachment",
]
