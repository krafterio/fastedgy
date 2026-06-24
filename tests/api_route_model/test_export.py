# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def test_export_csv_contains_headers_and_data(setup_http: httpx.AsyncClient) -> None:
    await setup_http.post("/api/test_categories", json={"name": "Books", "description": "stuff"})
    await setup_http.post("/api/test_categories", json={"name": "Movies"})

    response = await setup_http.get("/api/test_categories/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")

    lines = response.text.splitlines()

    assert "Name" in lines[0]
    assert any("Books" in line for line in lines[1:])
    assert any("Movies" in line for line in lines[1:])


async def test_export_supports_spreadsheet_formats(setup_http: httpx.AsyncClient) -> None:
    await setup_http.post("/api/test_categories", json={"name": "Books"})

    xlsx = await setup_http.get("/api/test_categories/export?format=xlsx")
    ods = await setup_http.get("/api/test_categories/export?format=ods")

    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers["content-type"]
    assert len(xlsx.content) > 0

    assert ods.status_code == 200
    assert "opendocument" in ods.headers["content-type"]
    assert len(ods.content) > 0


async def test_export_unsupported_format_is_rejected(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.get("/api/test_categories/export?format=pdf")

    assert response.status_code == 400
