# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import difflib

from pathlib import Path

from fastedgy.app import FastEdgy

from fastedgy.test.app import APP_VERSION, build_app, dump_openapi


SNAPSHOT_PATH = Path(__file__).resolve().parent / "snapshots" / "openapi.json"


def test_openapi_matches_committed_snapshot() -> None:
    expected = SNAPSHOT_PATH.read_text(encoding="utf-8")
    actual = dump_openapi(build_app())

    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile="tests/snapshots/openapi.json (committed)",
                tofile="openapi.json (current code)",
            )
        )

        raise AssertionError(
            "The generated OpenAPI specification drifted from the committed snapshot.\n"
            "If this change is intentional, regenerate the snapshot with `just gen-openapi`.\n\n" + diff
        )


def test_openapi_app_exposes_generated_routes(setup_openapi_app: FastEdgy) -> None:
    spec = setup_openapi_app.openapi()

    assert spec["info"]["version"] == APP_VERSION
    assert "/api/test_products" in spec["paths"]
    assert "/api/test_products/{item_id}" in spec["paths"]
    assert "/api/test_categories" in spec["paths"]


def test_openapi_schema_names_are_not_module_qualified(setup_openapi_app: FastEdgy) -> None:
    """Guard against schema-name collisions in the generated OpenAPI.

    When two different models share a ``__name__`` (typically a raw ORM model
    leaking into the schema next to its generated ``generate_output_model``
    counterpart), Pydantic disambiguates them by prefixing the module path, e.g.
    ``models__aisle__Aisle`` or ``fastedgy__api_route_model__action__generators__Aisle``.
    Such a name always starts with a lowercase module segment, whereas every
    legitimate schema (models, ``Pagination_*``, ``Body_*``, ``HTTPValidationError``)
    starts uppercase. A single leaked raw model poisons the whole namespace through
    its foreign-key closure, so a dependency bump that changes collision handling
    must not slip through unnoticed.
    """
    spec = setup_openapi_app.openapi()

    qualified = sorted(name for name in spec["components"]["schemas"] if name[:1].islower())

    assert not qualified, "module-qualified schema names signal a model name collision: " + ", ".join(qualified)
