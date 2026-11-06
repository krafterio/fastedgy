# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.login_throttle import LoginThrottleMixin


class LoginThrottle(LoginThrottleMixin):
    class Meta(LoginThrottleMixin.Meta):
        tablename = "login_throttles"


__all__ = [
    "LoginThrottle",
]
