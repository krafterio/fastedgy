# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.dependencies import register_service


class SudoChecker:
    """Project-overridable predicate for privileged (sudo) requests.

    The framework has no notion of a privileged user, so the default denies:
    register a subclass instance under this token
    (``register_service(MySudoChecker(), SudoChecker)``) to define what sudo
    means in the project (a user flag, a request state, an ACL...).
    """

    async def is_sudo(self) -> bool:
        return False


register_service(SudoChecker)


__all__ = [
    "SudoChecker",
]
