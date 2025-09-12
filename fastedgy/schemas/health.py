# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pydantic import BaseModel


class HealthResult(BaseModel):
    status: str


__all__ = [
    "HealthResult",
]
