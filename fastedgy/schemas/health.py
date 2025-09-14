# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pydantic import BaseModel


class Health(BaseModel):
    status: str


__all__ = [
    "Health",
]
