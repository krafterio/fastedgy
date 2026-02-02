# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from functools import wraps
from typing import TypeVar, Callable, Any, Coroutine
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry

T = TypeVar("T")


def transaction(
    func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    Decorator to wrap an async function in a database transaction.

    The transaction will:
    - COMMIT if the function completes successfully
    - ROLLBACK if an exception is raised

    Example:
        from fastedgy.orm.transaction import transaction

        @transaction
        async def patch_item_action(request, model_cls, item_id, item_data):
            item = await model_cls.query.get(id=item_id)
            item.name = item_data.name
            await item.save()

            # If error here, everything rolls back
            await notify_users(item)

            return item
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        db = get_service(Registry).database
        settings = get_service(BaseSettings)

        async with db.transaction(isolation_level=settings.database_isolation_level):
            return await func(*args, **kwargs)

    return wrapper


__all__ = [
    "transaction",
]
