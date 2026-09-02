# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""JSON-RPC plumbing shared by the MCP test modules."""

import json
from typing import Any

import httpx

PROTOCOL_VERSION = "2026-07-28"

# The stateless protocol replaces the handshake by an envelope every request
# carries: what the client speaks and what it can answer.
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
}


async def create_token(client: httpx.AsyncClient, name: str = "Agent") -> str:
    response = await client.post("/api/user-api-tokens", json={"name": name})
    assert response.status_code == 201, response.text

    return response.json()["token"]


async def rpc(
    client: httpx.AsyncClient,
    token: str,
    method: str,
    params: dict | None = None,
    header: str = "Authorization",
    expect_error: bool = False,
) -> dict:
    response = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": META}},
        headers={
            header: f"Bearer {token}" if header == "Authorization" else token,
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": method,
            # The routing header must echo what the body names: the tool for a
            # call, the URI for a resource read.
            **({"Mcp-Name": params["name"]} if params and "name" in params else {}),
            **({"Mcp-Name": params["uri"]} if params and "uri" in params else {}),
        },
    )
    # A JSON-RPC error travels on an HTTP 400; a tool that fails answers 200
    # with `isError`.
    assert response.status_code == (400 if expect_error else 200), response.text

    return response.json()


def payload(result: dict) -> Any:
    content = result["result"]["content"]
    assert content[0]["type"] == "text", content

    return json.loads(content[0]["text"])


__all__ = [
    "META",
    "PROTOCOL_VERSION",
    "create_token",
    "payload",
    "rpc",
]
