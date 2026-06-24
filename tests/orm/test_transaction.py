# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm import with_transaction
from fastedgy.test.models.category import Category


async def test_with_transaction_commits_the_unit(setup_db: FastEdgy) -> None:
    async def op() -> Category:
        category = Category(name="Committed")
        await category.save()

        return category

    result = await with_transaction(op)

    assert result.id is not None
    assert await Category.query.filter(Category.columns.name == "Committed").count() == 1


async def test_with_transaction_rolls_back_on_error(setup_db: FastEdgy) -> None:
    async def op() -> None:
        await Category(name="RolledBack").save()
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await with_transaction(op)

    assert await Category.query.filter(Category.columns.name == "RolledBack").count() == 0
