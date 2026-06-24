# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def test_delete_removes_the_item(setup_http: httpx.AsyncClient) -> None:
    created = (await setup_http.post("/api/test_categories", json={"name": "Temporary"})).json()

    response = await setup_http.delete(f"/api/test_categories/{created['id']}")

    assert response.status_code in (200, 204)

    follow_up = await setup_http.get(f"/api/test_categories/{created['id']}")

    assert follow_up.status_code == 404


async def test_delete_unknown_item_returns_404(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.delete("/api/test_categories/999999")

    assert response.status_code == 404
