# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime

from fastedgy.schemas import BaseModel


class UserApiTokenCreate(BaseModel):
    name: str
    expires_at: datetime | None = None


class UserApiTokenCreated(BaseModel):
    """The only response carrying the secret: it is hashed on the way in and
    cannot be read back afterwards."""

    id: int
    name: str
    token_hint: str
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    token: str


__all__ = [
    "UserApiTokenCreate",
    "UserApiTokenCreated",
]
