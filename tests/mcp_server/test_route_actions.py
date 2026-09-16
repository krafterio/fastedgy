# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A record tool honours the actions a model turns off in `api_route_model`."""

import pytest

from tests.mcp_server.helpers import payload, rpc

pytestmark = pytest.mark.anyio


async def _call(agent, tool: str, **arguments) -> dict:
    client, token, slug = agent

    return await rpc(
        client,
        token,
        "tools/call",
        {"name": tool, "arguments": {"model": "comment", "workspace": slug, **arguments}},
    )


async def test_a_tool_whose_route_is_off_is_refused(agent):
    from fastedgy.test.models.comment import Comment

    comment = Comment(content="Seeded")
    await comment.save()

    for tool, arguments in (
        ("create_record", {"values": {"content": "Via MCP"}}),
        ("update_record", {"id": comment.id, "values": {"content": "Renamed"}}),
        ("delete_record", {"id": comment.id}),
    ):
        result = (await _call(agent, tool, **arguments))["result"]

        assert result["isError"] is True, tool
        assert "HTTP 405" in result["content"][0]["text"], tool

    assert await Comment.query.count() == 1
    assert (await Comment.query.get(id=comment.id)).content == "Seeded"


async def test_a_tool_whose_route_is_on_still_answers(agent):
    from fastedgy.test.models.comment import Comment

    comment = Comment(content="Seeded")
    await comment.save()

    assert payload(await _call(agent, "get_record", id=comment.id))["content"] == "Seeded"
    assert payload(await _call(agent, "list_records"))["total"] == 1
