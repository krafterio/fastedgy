# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Union, get_args, get_origin

from fastedgy.app import FastEdgy
from fastedgy.api_route_model.action import (
    generate_input_create_model,
    generate_input_patch_model,
    generate_output_model,
)
from fastedgy.api_route_model.action.generators import (
    ForeignKeyInput,
    ForeignKeyObject,
    ForeignKeyOperation,
)

from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product
from fastedgy.test.models.queued_task import QueuedTask
from fastedgy.test.models.queued_task_log import QueuedTaskLog


def test_output_nullable_fk_is_model_or_object_or_null(setup_openapi_app: FastEdgy) -> None:
    annotation = generate_output_model(Product).model_fields["category"].annotation
    args = get_args(annotation)

    assert get_origin(annotation) is Union
    assert generate_output_model(Category) in args
    assert any(get_origin(arg) is dict for arg in args)
    assert type(None) in args


def test_output_required_fk_has_no_null(setup_openapi_app: FastEdgy) -> None:
    annotation = generate_output_model(QueuedTaskLog).model_fields["task"].annotation
    args = get_args(annotation)

    assert generate_output_model(QueuedTask) in args
    assert type(None) not in args


def test_output_self_referential_fk_does_not_recurse(setup_openapi_app: FastEdgy) -> None:
    # parent_task points back to QueuedTask: the model must reference itself.
    output = generate_output_model(QueuedTask)
    args = get_args(output.model_fields["parent_task"].annotation)

    assert output in args
    assert type(None) in args


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
