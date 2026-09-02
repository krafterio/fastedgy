# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A deployment that does not want a built-in tool names it at wiring time."""

import httpx
import pytest

from fastedgy.mcp import create_mcp_router
from tests.mcp_server.helpers import PROTOCOL_VERSION, create_token, rpc

pytestmark = pytest.mark.anyio


@pytest.fixture
async def restricted(setup_http: httpx.AsyncClient, workspace_env):
    """A second MCP endpoint on the same app, without the escape hatch."""
    from fastedgy.test.factories import authenticate

    user, workspace = workspace_env
    token = await create_token(authenticate(setup_http, user))
    setup_http.headers.pop("Authorization", None)

    app = setup_http._transport.app  # type: ignore[attr-defined]
    app.include_router(create_mcp_router(path="/restricted-mcp", disabled_tools=["request", "delete_record"]))

    try:
        yield setup_http, token, workspace.slug
    finally:
        app.router.routes = [route for route in app.router.routes if getattr(route, "path", "") != "/restricted-mcp"]


async def _restricted_rpc(client, token, method, params=None, expect_error=False):
    response = await client.post(
        "/restricted-mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {
                **(params or {}),
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": method,
            **({"Mcp-Name": params["name"]} if params and "name" in params else {}),
        },
    )
    assert response.status_code == (400 if expect_error else 200), response.text

    return response.json()


async def test_a_disabled_tool_leaves_the_catalogue(restricted):
    client, token, _ = restricted
    names = {tool["name"] for tool in (await _restricted_rpc(client, token, "tools/list"))["result"]["tools"]}

    assert "request" not in names
    assert "delete_record" not in names
    assert {"list_records", "get_model_info"} <= names


async def test_a_disabled_tool_is_not_callable_either(restricted):
    """A client may be working from a cached catalogue."""
    client, token, _ = restricted
    result = await _restricted_rpc(
        client,
        token,
        "tools/call",
        {"name": "request", "arguments": {"method": "GET", "path": "/api/dataset/metadatas"}},
        expect_error=True,
    )

    assert "Unknown tool 'request'" in result["error"]["message"]


async def test_the_untouched_endpoint_still_has_them(agent):
    client, token, _ = agent
    names = {tool["name"] for tool in (await rpc(client, token, "tools/list"))["result"]["tools"]}

    assert {"request", "delete_record"} <= names


def test_an_unknown_name_fails_at_wiring():
    with pytest.raises(ValueError, match="Unknown built-in MCP tool"):
        create_mcp_router(disabled_tools=["list_recordz"])
