# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A tool result can never carry a TTL; a resource read can. The catalogue is
exposed both ways so a client that caches has something to cache."""

import json

import pytest

from tests.mcp_server.helpers import rpc

pytestmark = pytest.mark.anyio


async def test_the_templates_carry_the_workspace(agent):
    client, token, _ = agent
    result = await rpc(client, token, "resources/templates/list")

    assert [template["uriTemplate"] for template in result["result"]["resourceTemplates"]] == [
        "fastedgy://models/{workspace}",
        "fastedgy://model/{workspace}/{model}",
    ]
    assert result["result"]["ttlMs"] == 3_600_000
    assert result["result"]["cacheScope"] == "public"


async def test_the_catalogue_reads_as_a_private_cacheable_resource(agent):
    client, token, slug = agent
    result = await rpc(client, token, "resources/read", {"uri": f"fastedgy://models/{slug}"})
    payload = json.loads(result["result"]["contents"][0]["text"])

    assert any(entry["name"] == "product" for entry in payload["models"])
    assert result["result"]["ttlMs"] == 300_000
    assert result["result"]["cacheScope"] == "private"


async def test_a_model_reads_as_a_private_cacheable_resource(agent):
    client, token, slug = agent
    result = await rpc(client, token, "resources/read", {"uri": f"fastedgy://model/{slug}/product"})
    payload = json.loads(result["result"]["contents"][0]["text"])

    assert payload["name"] == "product"
    assert payload["filter_syntax"]["examples"]
    assert result["result"]["cacheScope"] == "private"


async def test_the_tool_catalogue_is_publicly_cacheable(agent):
    client, token, _ = agent
    result = await rpc(client, token, "tools/list")

    assert result["result"]["ttlMs"] == 3_600_000
    assert result["result"]["cacheScope"] == "public"


async def test_a_resource_of_another_workspace_is_refused(agent):
    """The workspace sits in the URI, so two workspaces are two cache entries,
    and a slug the caller has no membership on resolves to nothing."""
    client, token, _ = agent
    result = await rpc(client, token, "resources/read", {"uri": "fastedgy://models/not-mine"}, expect_error=True)

    assert "No workspace 'not-mine'" in result["error"]["message"]


async def test_an_unknown_resource_is_refused(agent):
    client, token, _ = agent
    result = await rpc(client, token, "resources/read", {"uri": "fastedgy://nope"}, expect_error=True)

    assert "Unknown resource" in result["error"]["message"]


async def test_a_resource_reads_without_a_workspace(agent):
    """The slug is optional: without it the read covers what every workspace
    shares, and it is its own cache entry."""
    client, token, _ = agent

    catalogue = await rpc(client, token, "resources/read", {"uri": "fastedgy://models"})
    assert any(entry["name"] == "product" for entry in json.loads(catalogue["result"]["contents"][0]["text"])["models"])

    model = await rpc(client, token, "resources/read", {"uri": "fastedgy://model/product"})
    assert json.loads(model["result"]["contents"][0]["text"])["name"] == "product"
