# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).


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


__all__ = [
    "add_numbers",
    "boom",
    "make_category",
]
