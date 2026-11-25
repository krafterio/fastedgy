# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def test_export_csv_contains_headers_and_data(auth_http: httpx.AsyncClient) -> None:
    await auth_http.post("/api/test_categories", json={"name": "Books", "description": "stuff"})
    await auth_http.post("/api/test_categories", json={"name": "Movies"})

    response = await auth_http.get("/api/test_categories/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")

    lines = response.text.splitlines()

    assert "Name" in lines[0]
    assert any("Books" in line for line in lines[1:])
    assert any("Movies" in line for line in lines[1:])


async def test_export_supports_spreadsheet_formats(auth_http: httpx.AsyncClient) -> None:
    await auth_http.post("/api/test_categories", json={"name": "Books"})

    xlsx = await auth_http.get("/api/test_categories/export?format=xlsx")
    ods = await auth_http.get("/api/test_categories/export?format=ods")

    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers["content-type"]
    assert len(xlsx.content) > 0

    assert ods.status_code == 200
    assert "opendocument" in ods.headers["content-type"]
    assert len(ods.content) > 0


async def test_export_unsupported_format_is_rejected(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.get("/api/test_categories/export?format=pdf")

    assert response.status_code == 400


async def test_an_export_reads_and_writes_its_records_batch_by_batch(auth_http: httpx.AsyncClient, monkeypatch) -> None:
    """The records are read through one cursor a batch at a time, so an export holds one batch in
    memory: every record still comes out once and in order, in CSV as in XLSX."""
    import io

    import openpyxl

    from fastedgy.dataflow import exporter

    monkeypatch.setattr(exporter, "EXPORT_BATCH_SIZE", 2)

    for index in range(5):
        await auth_http.post("/api/test_categories", json={"name": f"Category {index}"})

    csv_export = await auth_http.get("/api/test_categories/export?format=csv&order_by=id")
    xlsx_export = await auth_http.get("/api/test_categories/export?format=xlsx&order_by=id&limit=3&offset=1")

    assert csv_export.status_code == 200, csv_export.text
    assert [line.split(",")[0] for line in csv_export.text.splitlines()[1:]] == [
        f"Category {index}" for index in range(5)
    ]

    assert xlsx_export.status_code == 200, xlsx_export.text
    sheet = openpyxl.load_workbook(io.BytesIO(xlsx_export.content)).active
    assert sheet is not None
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    assert [row[0] for row in rows] == [f"Category {index}" for index in range(1, 4)]
