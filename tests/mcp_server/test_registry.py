# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""What an application adds of its own: tools and resources, alongside the
built-in ones rather than in place of them."""

import json

import pytest

from fastedgy.dependencies import get_service
from fastedgy.mcp import McpRegistry, mcp_resource, mcp_tool
from tests.mcp_server.helpers import payload, rpc

pytestmark = pytest.mark.anyio


@pytest.fixture
def registry():
    """A registry emptied around each test: registration is process-wide."""
    registry = get_service(McpRegistry)
    tools, resources = dict(registry._tools), dict(registry._resources)
    registry._tools.clear()
    registry._resources.clear()

    yield registry

    registry._tools, registry._resources = tools, resources


async def test_a_registered_tool_joins_the_catalogue_and_answers(agent, registry):
    @mcp_tool(
        "shout",
        description="Shouts back what it is given.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )
    async def shout(arguments: dict) -> dict:
        return {"shouted": arguments["text"].upper()}

    client, token, _ = agent

    catalogue = await rpc(client, token, "tools/list")
    assert "shout" in {tool["name"] for tool in catalogue["result"]["tools"]}

    result = payload(await rpc(client, token, "tools/call", {"name": "shout", "arguments": {"text": "hello"}}))
    assert result == {"shouted": "HELLO"}


async def test_a_registered_resource_is_listed_and_read(agent, registry):
    @mcp_resource("note", uri_template="demo://note/{id}", description="A note.")
    async def read_note(uri: str) -> dict:
        return {"id": uri.rsplit("/", 1)[-1]}

    client, token, _ = agent

    templates = await rpc(client, token, "resources/templates/list")
    assert "demo://note/{id}" in {t["uriTemplate"] for t in templates["result"]["resourceTemplates"]}

    read = await rpc(client, token, "resources/read", {"uri": "demo://note/42"})
    assert json.loads(read["result"]["contents"][0]["text"]) == {"id": "42"}


async def test_the_built_in_tools_stay(agent, registry):
    @mcp_tool("extra", description="…", input_schema={"type": "object", "properties": {}})
    async def extra(arguments: dict) -> str:
        return "ok"

    client, token, _ = agent
    catalogue = await rpc(client, token, "tools/list")

    assert {"list_records", "get_model_info", "request", "extra"} <= {
        tool["name"] for tool in catalogue["result"]["tools"]
    }


def test_a_built_in_name_is_refused(registry):
    with pytest.raises(ValueError, match="already registered"):
        registry.register_tool("list_records", "…", {"type": "object"}, lambda arguments: None)


def test_a_built_in_uri_prefix_is_refused(registry):
    with pytest.raises(ValueError, match="collides"):
        registry.register_resource("mine", "fastedgy://model/mine/{id}", lambda uri: None)


def test_a_duplicate_name_is_refused(registry):
    registry.register_tool("twice", "…", {"type": "object"}, lambda arguments: None)

    with pytest.raises(ValueError, match="already registered"):
        registry.register_tool("twice", "…", {"type": "object"}, lambda arguments: None)
