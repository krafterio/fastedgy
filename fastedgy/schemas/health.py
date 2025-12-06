# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.schemas import BaseModel


class Health(BaseModel):
    status: str


__all__ = [
    "Health",
]
