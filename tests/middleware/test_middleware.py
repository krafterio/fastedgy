# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from starlette.requests import ClientDisconnect

from fastedgy.app import FastEdgy


async def test_client_disconnect_ends_the_request_quietly(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient, caplog
) -> None:
    async def vanishing_upload() -> None:
        # Simulates starlette raising ClientDisconnect while the endpoint
        # reads the request body (request.form(), request.json(), ...).
        raise ClientDisconnect()

    setup_db.add_api_route("/api/test-client-disconnect", vanishing_upload, methods=["POST"])

    response = await setup_http.post("/api/test-client-disconnect")

    assert response.status_code == 499
    assert not any(r.levelno >= 40 for r in caplog.records)
