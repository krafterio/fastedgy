# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def test_import_template_has_only_importable_headers(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.get("/api/test_categories/import/template?format=csv")

    assert response.status_code == 200

    lines = [line for line in response.text.splitlines() if line.strip()]

    assert lines[0] == "Name,Description"
    assert len(lines) == 1
