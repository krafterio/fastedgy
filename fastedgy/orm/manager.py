# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.models.managers import Manager, RedirectManager, BaseManager

from fastedgy.orm.query import QuerySet
from fastedgy.orm.filter.global_filters import apply_global_filters


class AccessControlManager(Manager):
    def get_queryset(self) -> QuerySet:
        return apply_global_filters(super().get_queryset())


class AccessControlRedirectManager(RedirectManager):
    def get_queryset(self) -> QuerySet:
        return apply_global_filters(super().get_queryset())


__all__ = [
    "BaseManager",
    "Manager",
    "RedirectManager",
    "AccessControlManager",
    "AccessControlRedirectManager",
]
