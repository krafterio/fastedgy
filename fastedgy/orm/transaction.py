# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
import random
from contextvars import ContextVar
from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, TypeVar, overload

from sqlalchemy.exc import DBAPIError

from fastedgy.dependencies import get_service
from fastedgy.orm import Registry

T = TypeVar("T")

logger = logging.getLogger("fastedgy.transaction")

# PostgreSQL SQLSTATE codes that are safe to retry by replaying the whole
# transactional unit (read + modify + write):
#   40001 = serialization_failure  ("could not serialize access ...", incl. the
#           SSI "canceled on identification as a pivot" variant)
#   40P01 = deadlock_detected
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})

# A serialization failure aborts the *whole* Postgres transaction, not just a
# savepoint. Only the outermost call can therefore retry meaningfully; nested
# ones run once and let the root replay the entire unit. Task-local (ContextVar)
# so concurrent requests/workers never see each other's flag.
_in_retrying_transaction: ContextVar[bool] = ContextVar(
    "fastedgy_in_retrying_transaction", default=False
)


def is_serialization_error(exc: BaseException) -> bool:
    """Return True for transient Postgres serialization/deadlock errors.

    These carry SQLSTATE 40001/40P01, and Postgres's own hint says they
    "might succeed if retried" — but only when the entire read-modify-write
    unit is replayed so that reads observe fresh data. Retrying just the
    failing statement reissues stale values and silently defeats SERIALIZABLE.
    """
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate in _RETRYABLE_SQLSTATES:
        return True
    # Fallback on the message when the driver doesn't surface a sqlstate.
    text = f"{exc} {orig}".lower()
    return "could not serialize access" in text or "deadlock detected" in text


async def with_transaction(
    factory: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 0.05,
    isolation_level: str | None = None,
) -> T:
    """Run ``factory()`` inside a database transaction, replaying it on conflict.

    On a transient serialization/deadlock conflict (SQLSTATE 40001/40P01) the
    **whole callable is replayed** in a fresh transaction (up to ``retries``
    extra attempts, exponential backoff + jitter). Replaying the entire callable
    — not just the failing statement — is what makes the retry correct: every
    read it performs is re-executed against fresh data, so the retry boundary is
    the full read-modify-write unit, the only place a serialization failure can
    be retried without reintroducing lost updates.

    This is the callable form shared by the :func:`transaction` decorator; use
    it to scope the retry precisely around a block — typically the DB
    read-modify-write of a task whose expensive/external work must stay out of
    the replayed region.

    Args:
        factory: A zero-arg async callable holding the read-modify-write. It is
            re-invoked on each attempt, so keep non-database side effects (HTTP,
            push, payment captures, ...) OUTSIDE it — they would otherwise be
            repeated on every retry.
        retries: Extra attempts after the first (total tries = ``retries + 1``).
        base_delay: Base backoff in seconds (exponential, with jitter).
        isolation_level: Optional Postgres isolation level for the transaction
            (e.g. ``"READ COMMITTED"`` to avoid the conflict instead of retrying
            it). Defaults to the databasez default (``SERIALIZABLE``). Ignored
            for a nested call — a savepoint inherits the outer level.

    Example:
        async def _persist():
            spot = await Spot.query.get_or_none(id=spot_id)  # re-read on retry
            if not spot or spot.position is not None:
                return
            spot.position = (lat, lng)
            await spot.save()

        await with_transaction(_persist)
    """
    db = get_service(Registry).database

    # Nested call → savepoint only. A serialization failure poisons the whole
    # transaction, so retrying here is futile; let the outermost call replay.
    if _in_retrying_transaction.get():
        async with db.transaction():
            return await factory()

    token = _in_retrying_transaction.set(True)
    try:
        for attempt in range(retries + 1):
            try:
                tx = (
                    db.transaction(isolation_level=isolation_level)
                    if isolation_level is not None
                    else db.transaction()
                )
                async with tx:
                    return await factory()
            except DBAPIError as e:
                if attempt == retries or not is_serialization_error(e):
                    raise
                delay = base_delay * (2**attempt) + random.uniform(0, base_delay)
                logger.debug(
                    "Serialization conflict in %s, retry %d/%d in %.3fs",
                    getattr(factory, "__qualname__", factory),
                    attempt + 1,
                    retries,
                    delay,
                )
                await asyncio.sleep(delay)
    finally:
        _in_retrying_transaction.reset(token)
    # The loop above always returns or raises.
    raise AssertionError("unreachable")  # pragma: no cover


@overload
def transaction(
    func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]: ...


@overload
def transaction(
    *,
    retries: int = ...,
    base_delay: float = ...,
    isolation_level: str | None = ...,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]
]: ...


def transaction(
    func: Callable[..., Coroutine[Any, Any, T]] | None = None,
    *,
    retries: int = 3,
    base_delay: float = 0.05,
    isolation_level: str | None = None,
) -> Any:
    """
    Decorator to wrap an async function in a database transaction.

    The transaction will:
    - COMMIT if the function completes successfully
    - ROLLBACK if an exception is raised

    On a transient serialization/deadlock conflict the whole decorated function
    is replayed (see :func:`with_transaction`, of which this is the decorator
    sugar). Use it for functions whose body is the read-modify-write unit
    (most API actions, pure-DB tasks). For functions that perform expensive or
    external work before their write, prefer calling :func:`with_transaction`
    around just the write so that work is not replayed.

    Caveat: non-database side effects inside the function are repeated on each
    retry. Nested ``@transaction`` calls run as a single savepoint within the
    outermost transaction; only that outermost one owns the retry loop.

    Examples:
        @transaction
        async def patch_item_action(request, model_cls, item_id, item_data):
            item = await model_cls.query.get(id=item_id)   # re-read on retry
            item.name = item_data.name
            await item.save()
            return item

        @transaction(retries=5, isolation_level="READ COMMITTED")
        async def heavy_contended_update(...):
            ...
    """

    def decorator(
        fn: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await with_transaction(
                lambda: fn(*args, **kwargs),
                retries=retries,
                base_delay=base_delay,
                isolation_level=isolation_level,
            )

        return wrapper

    # Support both @transaction and @transaction(retries=..., isolation_level=...)
    return decorator(func) if func is not None else decorator


__all__ = [
    "transaction",
    "with_transaction",
    "is_serialization_error",
]
