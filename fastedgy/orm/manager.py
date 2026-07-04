# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.models.managers import Manager, RedirectManager, BaseManager

from fastedgy.orm.query import QuerySet
from fastedgy.orm.access_guard import ModelAction, acheck_access, check_access
from fastedgy.orm.filter.global_filters import apply_global_filters


class AccessControlQuerySet(QuerySet):
    """QuerySet used by the access-controlled managers: bulk writes go through
    the access guards like instance writes do. Guards receive no instance, so
    row-conditional write exemptions do not apply to bulk operations."""

    async def update(self, **kwargs: Any) -> None:
        await acheck_access(self.model_class, ModelAction.update)
        return await super().update(**kwargs)

    async def delete(self, use_models: bool = False) -> int:
        await acheck_access(self.model_class, ModelAction.delete)
        return await super().delete(use_models=use_models)


class AccessControlManager(Manager):
    queryset_class = AccessControlQuerySet

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        check_access(queryset.model_class, ModelAction.read)
        return apply_global_filters(queryset)


class AccessControlRedirectManager(RedirectManager):
    queryset_class = AccessControlQuerySet

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        check_access(queryset.model_class, ModelAction.read)
        return apply_global_filters(queryset)


__all__ = [
    "BaseManager",
    "Manager",
    "RedirectManager",
    "AccessControlManager",
    "AccessControlQuerySet",
    "AccessControlRedirectManager",
]
