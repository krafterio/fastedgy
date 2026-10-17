# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.orm.relations.processor import process_relation_operations
from fastedgy.test.models.assignment import Assignment
from fastedgy.test.models.category import Category


async def test_a_child_whose_key_is_required_is_deleted_without_being_unlinked(setup_db: FastEdgy) -> None:
    category = await Category.query.create(name="Bikes")
    kept = await Assignment.query.create(label="kept", category=category)
    gone = await Assignment.query.create(label="gone", category=category)

    await process_relation_operations(category, "assignments", [["delete", gone.id]], Assignment)

    assert [assignment.id for assignment in await Assignment.query.all()] == [kept.id]

