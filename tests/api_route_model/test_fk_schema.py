# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Union, get_args, get_origin

from fastedgy.app import FastEdgy
from fastedgy.api_route_model.action import (
    generate_input_create_model,
    generate_input_patch_model,
    generate_output_model,
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


def test_input_fk_is_an_integer(setup_openapi_app: FastEdgy) -> None:
    # A foreign key is set on input with the related record id only (no object).
    create_annotation = generate_input_create_model(Product).model_fields["category"].annotation
    assert int in get_args(create_annotation) or create_annotation is int

    patch_annotation = generate_input_patch_model(Product).model_fields["category"].annotation
    assert int in get_args(patch_annotation)
