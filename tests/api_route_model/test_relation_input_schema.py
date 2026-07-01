# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Request-body schema and validation for relation inputs (simple + advanced mode).

Runtime behaviour of the operations lives in test_fk_input.py / test_patch.py; here
we guard the generated OpenAPI request bodies (foreign key: id | object | operation;
collection: list of ids | list of operations) and the Pydantic validation of every
documented form — and that ``FastEdgy.openapi()``'s orphan pruning keeps the shared
operation models (``ForeignKeyObject`` / ``ForeignKeyOperation`` / ``RelationOperation``).
"""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from fastedgy.app import FastEdgy
from fastedgy.api_route_model.action import (
    generate_input_create_model,
    generate_input_patch_model,
)

from fastedgy.test.models.product import Product  # nullable FK `category`, M2M `tags`


def _variant_kinds(prop: dict[str, Any]) -> set[str]:
    """Normalize a JSON-schema property's ``anyOf`` into a set of kind tags."""
    kinds: set[str] = set()

    for variant in prop.get("anyOf", [prop]):
        if "$ref" in variant:
            kinds.add("ref:" + variant["$ref"].rsplit("/", 1)[-1])
        elif variant.get("type") == "null":
            kinds.add("null")
        elif variant.get("type") == "integer":
            kinds.add("int")
        elif variant.get("type") == "array":
            items = variant.get("items", {})
            if "$ref" in items:
                kinds.add("array:ref:" + items["$ref"].rsplit("/", 1)[-1])
            elif items.get("type") == "integer":
                kinds.add("array:int")
            else:
                kinds.add("array:other")
        else:
            kinds.add(variant.get("type", "other"))

    return kinds


def _properties(spec: dict[str, Any], schema_name: str) -> dict[str, Any]:
    return spec["components"]["schemas"][schema_name]["properties"]


# --- OpenAPI request-body schema ------------------------------------------------


def test_nullable_fk_create_schema_documents_every_input_form(setup_openapi_app: FastEdgy) -> None:
    props = _properties(setup_openapi_app.openapi(), "Product-Create")

    assert _variant_kinds(props["category"]) == {
        "int",  # link by id
        "ref:ForeignKeyObject",  # link by object / link + update
        "ref:ForeignKeyOperation",  # advanced: [action, value]
        "null",  # unlink
    }


def test_nullable_fk_update_schema_documents_every_input_form(setup_openapi_app: FastEdgy) -> None:
    props = _properties(setup_openapi_app.openapi(), "Product-Update")

    assert _variant_kinds(props["category"]) == {
        "int",
        "ref:ForeignKeyObject",
        "ref:ForeignKeyOperation",
        "null",
    }


def test_required_fk_create_schema_excludes_null(setup_openapi_app: FastEdgy) -> None:
    props = _properties(setup_openapi_app.openapi(), "QueuedTaskLog-Create")
    kinds = _variant_kinds(props["task"])

    assert {"int", "ref:ForeignKeyObject", "ref:ForeignKeyOperation"} <= kinds
    assert "null" not in kinds


def test_collection_create_schema_documents_simple_and_advanced(setup_openapi_app: FastEdgy) -> None:
    props = _properties(setup_openapi_app.openapi(), "Product-Create")
    kinds = _variant_kinds(props["tags"])

    assert "array:int" in kinds  # simple mode: [1, 2, 3]
    assert "array:ref:RelationOperation" in kinds  # advanced mode: [["link", 1], ...]


def test_collection_update_schema_documents_simple_and_advanced(setup_openapi_app: FastEdgy) -> None:
    props = _properties(setup_openapi_app.openapi(), "Product-Update")
    kinds = _variant_kinds(props["tags"])

    assert "array:int" in kinds
    assert "array:ref:RelationOperation" in kinds


def test_operation_models_survive_orphan_pruning(setup_openapi_app: FastEdgy) -> None:
    # FastEdgy.openapi() prunes orphan schemas; the shared advanced-mode operation
    # models are referenced by the generated input bodies and must not be dropped.
    schemas = setup_openapi_app.openapi()["components"]["schemas"]

    for name in ("ForeignKeyObject", "ForeignKeyOperation", "RelationOperation"):
        assert name in schemas


def test_pruning_leaves_no_dangling_ref(setup_openapi_app: FastEdgy) -> None:
    spec = setup_openapi_app.openapi()
    schemas = spec["components"]["schemas"]
    referenced: set[str] = set()

    def collect(node: object) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and "/schemas/" in ref:
                referenced.add(ref.rsplit("/", 1)[-1])
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(spec)
    dangling = sorted(name for name in referenced if name not in schemas)

    assert not dangling, "pruning removed a referenced schema: " + ", ".join(dangling)


# --- Pydantic validation of every documented input form -------------------------


def _fk_adapter(create: bool = True) -> TypeAdapter[Any]:
    generate = generate_input_create_model if create else generate_input_patch_model
    return TypeAdapter(generate(Product).model_fields["category"].annotation)


def _collection_adapter(create: bool = True) -> TypeAdapter[Any]:
    generate = generate_input_create_model if create else generate_input_patch_model
    return TypeAdapter(generate(Product).model_fields["tags"].annotation)


@pytest.mark.parametrize(
    "value",
    [
        5,  # link by id
        {"id": 5},  # link by object
        {"id": 5, "name": "Phones"},  # link + update
        None,  # unlink (nullable)
        ["link", 5],
        ["unlink"],
        ["create", {"name": "Phones"}],
        ["update", {"id": 5, "name": "Renamed"}],
        ["delete", 5],
    ],
)
def test_foreign_key_input_accepts_documented_forms(setup_openapi_app: FastEdgy, value: Any) -> None:
    _fk_adapter().validate_python(value)


@pytest.mark.parametrize(
    "value",
    [
        ["link"],  # missing value
        ["delete"],  # missing value
        ["unlink", 5],  # value where none expected
        ["bogus", 5],  # unknown action
        [],  # empty operation
    ],
)
def test_foreign_key_input_rejects_malformed(setup_openapi_app: FastEdgy, value: Any) -> None:
    with pytest.raises(ValidationError):
        _fk_adapter().validate_python(value)


@pytest.mark.parametrize(
    "value",
    [
        [1, 2, 3],  # simple mode
        [["link", 1]],
        [["unlink", 1]],
        [["set", [1, 2, 3]]],
        [["clear"]],
        [["create", {"name": "New"}]],
        [["update", {"id": 1, "name": "Updated"}]],
        [["delete", 1]],
        [["clear"], ["link", 1], ["create", {"name": "New"}]],  # ordered mix
    ],
)
def test_collection_input_accepts_documented_forms(setup_openapi_app: FastEdgy, value: Any) -> None:
    _collection_adapter().validate_python(value)


@pytest.mark.parametrize(
    "value",
    [
        [["link"]],  # missing value
        [["bogus"]],  # unknown action
        [["clear", 1]],  # value where none expected
        [["set", 5]],  # set expects a list of ids
    ],
)
def test_collection_input_rejects_malformed(setup_openapi_app: FastEdgy, value: Any) -> None:
    with pytest.raises(ValidationError):
        _collection_adapter().validate_python(value)


def test_patch_forms_match_create_forms(setup_openapi_app: FastEdgy) -> None:
    # PATCH accepts the same operations as POST (plus null everywhere, being optional).
    _fk_adapter(create=False).validate_python(["update", {"id": 5, "name": "Renamed"}])
    _collection_adapter(create=False).validate_python([["link", 1], ["unlink", 2]])
