# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields


@api_route_model(sync={"mode": "partial"})
class Ticket(BaseModel):
    """Partially replicated model with a server-generated reference.

    Exercises the offline pair a client needs to create records while
    disconnected: a ``partial`` replication regime (nothing pre-downloaded) and
    a ``read_only`` reference carrying the placeholder the client shows until
    the server assigns the real value.
    """

    reference = fields.CharField(
        max_length=50,
        null=True,
        read_only=True,
        local_placeholder="DRAFT-{seq}",
    )
    subject = fields.CharField(max_length=200)

    class Meta(BaseModel.Meta):
        tablename = "test_tickets"


__all__ = [
    "Ticket",
]
