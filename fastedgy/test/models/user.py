# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.user import BaseUser


@api_route_model()
class User(BaseUser):
    class Meta(BaseUser.Meta):
        tablename = "users"


__all__ = [
    "User",
]
