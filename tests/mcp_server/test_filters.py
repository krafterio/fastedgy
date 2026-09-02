# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Building a filter is what an agent gets wrong first: the grammar travels with
the tool schema, with the model info and with a rejection."""

import pytest

from tests.mcp_server.helpers import payload, rpc

pytestmark = pytest.mark.anyio


async def _products(agent, *names: str) -> None:
    client, token, slug = agent

    for name in names:
        await rpc(
            client,
            token,
            "tools/call",
            {
                "name": "create_record",
                "arguments": {"model": "product", "workspace": slug, "values": {"name": name, "price": "1.00"}},
            },
        )


async def test_a_rule_filters(agent):
    client, token, slug = agent
    await _products(agent, "Alpha", "Beta")

    matched = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {
                "name": "list_records",
                "arguments": {"model": "product", "workspace": slug, "filter": ["name", "ilike", "%lph%"]},
            },
        )
    )

    assert [item["name"] for item in matched["items"]] == ["Alpha"]


async def test_a_group_filters(agent):
    client, token, slug = agent
    await _products(agent, "Alpha", "Beta", "Gamma")

    matched = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {
                "name": "list_records",
                "arguments": {
                    "model": "product",
                    "workspace": slug,
                    "filter": ["|", [["name", "=", "Alpha"], ["name", "=", "Beta"]]],
                },
            },
        )
    )

    assert sorted(item["name"] for item in matched["items"]) == ["Alpha", "Beta"]


async def test_a_group_also_takes_the_english_spelling(agent):
    """No agent writes `&` spontaneously; `and` is taken for what it means."""
    client, token, slug = agent
    await _products(agent, "Alpha", "Beta")

    matched = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {
                "name": "list_records",
                "arguments": {
                    "model": "product",
                    "workspace": slug,
                    "filter": ["and", [["name", "=", "Alpha"], ["is_active", "is true"]]],
                },
            },
        )
    )

    assert [item["name"] for item in matched["items"]] == ["Alpha"]


async def test_a_broken_filter_answers_with_the_grammar(agent):
    client, token, slug = agent
    result = await rpc(
        client,
        token,
        "tools/call",
        {
            "name": "list_records",
            "arguments": {"model": "product", "workspace": slug, "filter": ["name", "=", "x", "extra", "junk"]},
        },
    )

    assert result["result"]["isError"] is True
    assert "Expected shape" in result["result"]["content"][0]["text"]


async def test_model_info_carries_the_grammar_and_the_operators(agent):
    client, token, slug = agent
    metadata = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {"name": "get_model_info", "arguments": {"model": "product", "workspace": slug}},
        )
    )

    assert metadata["filter_syntax"]["group"][0].startswith("&")
    assert metadata["fields"]["name"]["filter_operators"]
    assert metadata["resource_uri"] == f"fastedgy://model/{slug}/product"
