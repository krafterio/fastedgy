# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.relations.processor import process_relation_operations
from fastedgy.orm.relations.utils import RelationOperationError
from fastedgy.test.models.assignment import Assignment
from fastedgy.test.models.category import Category
from fastedgy.test.models.comment import Comment
from fastedgy.test.models.product import Product


async def test_a_child_whose_key_is_required_is_deleted_without_being_unlinked(setup_db: FastEdgy) -> None:
    category = await Category.query.create(name="Bikes")
    kept = await Assignment.query.create(label="kept", category=category)
    gone = await Assignment.query.create(label="gone", category=category)

    await process_relation_operations(category, "assignments", [["delete", gone.id]], Assignment)

    assert [assignment.id for assignment in await Assignment.query.all()] == [kept.id]


async def test_unlink_and_delete_act_on_the_records_of_the_relation(setup_db: FastEdgy) -> None:
    first = await Product.query.create(name="First", price="9.99")
    second = await Product.query.create(name="Second", price="9.99")
    comment = await Comment.query.create(content="on the second", product=second)

    for action in ("unlink", "delete"):
        with pytest.raises(RelationOperationError, match="not linked"):
            await process_relation_operations(first, "comments", [[action, comment.id]], Comment)

    stored = await Comment.query.get(id=comment.id)

    assert stored.product.id == second.id
