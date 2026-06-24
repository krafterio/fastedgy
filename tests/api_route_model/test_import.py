# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


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
