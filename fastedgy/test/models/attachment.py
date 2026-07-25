# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import fields
from fastedgy.models.attachment import AttachmentPathMixin
from fastedgy.api_route_model import api_route_model


@api_route_model()
class Attachment(AttachmentPathMixin):
    # Polymorphic owner: exercises associating an attachment at upload time,
    # through the `meta` form field, instead of a follow-up PATCH.
    record = fields.GenericForeignKey(to=["Product"], related_name="attachments", null=True)

    class Meta(AttachmentPathMixin.Meta):
        tablename = "attachments"


__all__ = [
    "Attachment",
]
