# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from fastedgy.app import FastEdgy


def test_import_body_schema_is_shared(setup_openapi_app: FastEdgy) -> None:
    spec = setup_openapi_app.openapi()
    schemas = spec["components"]["schemas"]

    assert "ImportItemsBody" in schemas
    assert not [name for name in schemas if name.startswith("Body_import_items")]

    refs = {
        next(iter(item["post"]["requestBody"]["content"].values()))["schema"]["$ref"]
        for path, item in spec["paths"].items()
        if path.endswith("/import") and "post" in item
    }

    assert refs == {"#/components/schemas/ImportItemsBody"}


async def test_import_creates_records_from_csv(auth_http: httpx.AsyncClient) -> None:
    header = (await auth_http.get("/api/test_categories/import/template?format=csv")).text.splitlines()[0]

    csv_content = header + "\nImported A,desc A\nImported B,desc B\n"

    response = await auth_http.post(
        "/api/test_categories/import",
        files={"file": ("data.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200

    result = response.json()

    assert result["success"] == 2
    assert result["created"] == 2
    assert result["errors"] == 0
    assert set(result) >= {"success", "errors", "created", "updated", "error_details"}

    listing = (await auth_http.get("/api/test_categories")).json()

    assert listing["total"] == 2
    assert {item["name"] for item in listing["items"]} == {"Imported A", "Imported B"}
