# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The MCP transport: a personal API key opens it, and its tools go through the
same actions as the generated REST routes."""

import httpx
import pytest

from tests.mcp_server.helpers import PROTOCOL_VERSION, payload, rpc

pytestmark = pytest.mark.anyio


async def test_a_key_opens_the_transport(agent):
    client, token, _ = agent
    result = await rpc(client, token, "tools/list")
    names = {tool["name"] for tool in result["result"]["tools"]}

    assert {"list_workspaces", "list_models", "get_model_info", "list_records", "request"} <= names


async def test_the_transport_refuses_an_unknown_key(setup_http: httpx.AsyncClient):
    response = await setup_http.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Authorization": "Bearer fet_nope", "MCP-Protocol-Version": PROTOCOL_VERSION},
    )

    assert response.status_code == 401


async def test_the_key_also_travels_on_the_api_token_header(agent):
    """A host that keeps `Authorization` for its own OAuth token, Claude App
    among them, can only add one extra header."""
    client, token, _ = agent
    result = await rpc(client, token, "tools/list", header="X-Api-Token")

    assert {tool["name"] for tool in result["result"]["tools"]} >= {"list_models", "request"}


async def test_the_catalogue_is_scoped_to_a_workspace(agent):
    client, token, slug = agent

    workspaces = payload(await rpc(client, token, "tools/call", {"name": "list_workspaces", "arguments": {}}))
    assert [entry["slug"] for entry in workspaces] == [slug]

    models = payload(await rpc(client, token, "tools/call", {"name": "list_models", "arguments": {"workspace": slug}}))
    assert any(entry["name"] == "product" for entry in models["models"])
    assert models["resource_uri"] == f"fastedgy://models/{slug}"


async def test_a_foreign_workspace_is_refused(agent):
    client, token, _ = agent
    result = await rpc(
        client,
        token,
        "tools/call",
        {"name": "list_records", "arguments": {"model": "product", "workspace": "not-mine"}},
    )

    assert result["result"]["isError"] is True
    assert "not-mine" in result["result"]["content"][0]["text"]


async def test_write_lifecycle(agent):
    client, token, slug = agent

    created = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {
                "name": "create_record",
                "arguments": {
                    "model": "product",
                    "workspace": slug,
                    "values": {"name": "Via MCP", "price": "10.00"},
                },
            },
        )
    )
    assert created["name"] == "Via MCP"

    updated = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {
                "name": "update_record",
                "arguments": {
                    "model": "product",
                    "workspace": slug,
                    "id": created["id"],
                    "values": {"name": "Renamed"},
                },
            },
        )
    )
    assert updated["name"] == "Renamed"

    fetched = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {"name": "get_record", "arguments": {"model": "product", "workspace": slug, "id": created["id"]}},
        )
    )
    assert fetched["name"] == "Renamed"

    result = await rpc(
        client,
        token,
        "tools/call",
        {"name": "delete_record", "arguments": {"model": "product", "workspace": slug, "id": created["id"]}},
    )
    assert result["result"]["content"][0]["text"] == "Deleted"

    records = payload(
        await rpc(
            client, token, "tools/call", {"name": "list_records", "arguments": {"model": "product", "workspace": slug}}
        )
    )
    assert records["total"] == 0


async def test_request_reaches_any_endpoint_with_the_caller_rights(agent):
    client, token, _ = agent
    result = await rpc(
        client,
        token,
        "tools/call",
        {"name": "request", "arguments": {"method": "GET", "path": "/api/dataset/metadatas"}},
    )
    text = result["result"]["content"][0]["text"]

    assert text.startswith("HTTP 200")
    assert "product" in text


async def test_the_mcp_endpoint_cannot_call_itself(agent):
    client, token, _ = agent
    result = await rpc(
        client, token, "tools/call", {"name": "request", "arguments": {"method": "POST", "path": "/mcp"}}
    )

    assert result["result"]["isError"] is True
    assert "cannot call itself" in result["result"]["content"][0]["text"]


async def test_the_catalogue_answers_without_a_workspace(agent):
    """An agent calls `get_model_info` before it has picked a workspace: a
    workspace only adds fields, so the answer stands without one."""
    client, token, _ = agent

    models = payload(await rpc(client, token, "tools/call", {"name": "list_models", "arguments": {}}))
    assert any(entry["name"] == "product" for entry in models["models"])

    metadata = payload(
        await rpc(client, token, "tools/call", {"name": "get_model_info", "arguments": {"model": "product"}})
    )
    assert metadata["fields"]["name"]["filter_operators"]
    assert metadata["resource_uri"] == "fastedgy://model/product"


async def test_a_record_tool_still_demands_a_workspace(agent):
    client, token, _ = agent
    result = await rpc(client, token, "tools/call", {"name": "list_records", "arguments": {"model": "product"}})

    assert result["result"]["isError"] is True
    assert "`workspace` slug is required" in result["result"]["content"][0]["text"]


def test_the_mcp_router_refuses_to_mount_without_api_keys(monkeypatch: pytest.MonkeyPatch):
    """A JWT expires in minutes: without keys the endpoint would be there and
    unreachable, so the wiring fails loudly instead."""
    import fastedgy.models.user_api_token as module
    from fastedgy.mcp import create_mcp_router

    monkeypatch.setattr(module, "find_user_api_token_model", lambda: None)

    with pytest.raises(RuntimeError, match="user_api_tokens=True"):
        create_mcp_router()
