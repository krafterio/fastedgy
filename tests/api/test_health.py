# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def test_health_returns_ok(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_requires_authentication(setup_http: httpx.AsyncClient) -> None:
    assert (await setup_http.get("/api/health")).status_code == 401
