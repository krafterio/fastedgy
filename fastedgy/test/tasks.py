# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import threading

_blocking_sync_release = threading.Event()


def add_numbers(a: int, b: int) -> int:
    return a + b


def boom(message: str = "boom") -> None:
    raise ValueError(message)


async def make_category(name: str) -> int:
    from fastedgy.test.models.category import Category

    category = Category(name=name)
    await category.save()

    assert category.id is not None

    return category.id


def blocking_sync(timeout: float = 30.0) -> str:
    """Sync task that blocks its executor thread until released."""
    _blocking_sync_release.wait(timeout)

    return "released"


def release_blocking_sync() -> None:
    _blocking_sync_release.set()


def reset_blocking_sync() -> None:
    _blocking_sync_release.clear()


__all__ = [
    "add_numbers",
    "blocking_sync",
    "boom",
    "make_category",
    "release_blocking_sync",
    "reset_blocking_sync",
]
