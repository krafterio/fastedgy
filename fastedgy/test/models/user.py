# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.user import BaseUser
from fastedgy.api_route_model import api_route_model


@api_route_model()
class User(BaseUser):
    class Meta(BaseUser.Meta):
        tablename = "users"


__all__ = [
    "User",
]
