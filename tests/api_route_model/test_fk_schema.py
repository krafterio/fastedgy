# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import get_args

from fastedgy.app import FastEdgy
from fastedgy.api_route_model.action import (
    generate_input_create_model,
    generate_input_patch_model,
)
from fastedgy.api_route_model.action.generators import (
    ForeignKeyInput,
    ForeignKeyObject,
    ForeignKeyOperation,
)

from fastedgy.test.models.product import Product
from fastedgy.test.models.queued_task_log import QueuedTaskLog


def test_input_nullable_fk_accepts_id_object_operation_or_null(setup_openapi_app: FastEdgy) -> None:
    # category is nullable: id (link), object (link + update), operation, or null.
    annotation = generate_input_create_model(Product).model_fields["category"].annotation
    args = get_args(annotation)

    assert int in args
    assert ForeignKeyObject in args
    assert ForeignKeyOperation in args
    assert type(None) in args


def test_input_patch_fk_accepts_null_to_unlink(setup_openapi_app: FastEdgy) -> None:
    annotation = generate_input_patch_model(Product).model_fields["category"].annotation
    args = get_args(annotation)

    assert int in args
    assert ForeignKeyObject in args
    assert ForeignKeyOperation in args
    assert type(None) in args


def test_input_required_fk_excludes_null(setup_openapi_app: FastEdgy) -> None:
    # task is a required foreign key: it cannot be unlinked, so null is not allowed.
    annotation = generate_input_create_model(QueuedTaskLog).model_fields["task"].annotation
    args = get_args(annotation)

    assert annotation is ForeignKeyInput or (int in args and type(None) not in args)
