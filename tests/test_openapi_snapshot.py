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
