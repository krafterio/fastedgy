# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.api_route_model.action import (
    generate_input_create_model,
    generate_input_patch_model,
    is_exposed_relation_field,
)

from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product
from fastedgy.test.models.queued_task import QueuedTask
from fastedgy.test.models.workspace import Workspace


def _output_schema_props(model_cls) -> dict:
    """The response shape a model exposes: the properties of its serialization
    JSON schema, enriched by ``BaseModel.__get_pydantic_json_schema__``
    (exposed relations included, ORM-internal reverse accessors hidden)."""
    schema = model_cls.model_json_schema(mode="serialization")

    if "properties" in schema:
        return schema["properties"]

    return schema["$defs"][schema["$ref"].rsplit("/", 1)[-1]]["properties"]


def _input_models(model_cls):
    return (generate_input_create_model(model_cls), generate_input_patch_model(model_cls))


def test_auto_generated_reverse_relation_is_hidden(setup_openapi_app: FastEdgy) -> None:
    # `queuedtasks_set` is Edgy's auto-generated reverse accessor for the self
    # foreign key; it is an ORM internal and must stay out of the API schemas.
    assert "queuedtasks_set" not in _output_schema_props(QueuedTask)
    assert "logs" in _output_schema_props(QueuedTask)

    for generated in _input_models(QueuedTask):
        assert "queuedtasks_set" not in generated.model_fields
        assert "logs" in generated.model_fields


def test_disabled_reverse_relation_is_hidden(setup_openapi_app: FastEdgy) -> None:
    # The workspace foreign key declares `related_name="+"` (no reverse relation),
    # so the `+` placeholder must never surface as an API field.
    assert "+" not in _output_schema_props(Workspace)
    assert "workspace_users" in _output_schema_props(Workspace)

    for generated in _input_models(Workspace):
        assert "+" not in generated.model_fields
        assert "workspace_users" in generated.model_fields


def test_explicit_and_m2m_relations_are_exposed(setup_openapi_app: FastEdgy) -> None:
    assert "tags" in _output_schema_props(Product)
    assert "products" in _output_schema_props(Category)

    for generated in _input_models(Product):
        assert "tags" in generated.model_fields

    for generated in _input_models(Category):
        assert "products" in generated.model_fields


def test_is_exposed_relation_field_classification(setup_openapi_app: FastEdgy) -> None:
    assert is_exposed_relation_field(QueuedTask.model_fields["logs"]) is True
    assert is_exposed_relation_field(QueuedTask.model_fields["queuedtasks_set"]) is False
    assert is_exposed_relation_field(Workspace.model_fields["+"]) is False
    assert is_exposed_relation_field(Product.model_fields["tags"]) is True
    assert is_exposed_relation_field(Product.model_fields["name"]) is False
