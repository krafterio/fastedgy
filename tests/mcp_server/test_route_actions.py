# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A record tool honours the actions a model turns off in `api_route_model`."""

import copy

import pytest

from fastedgy.dependencies import get_service
from tests.mcp_server.helpers import payload, rpc

pytestmark = pytest.mark.anyio


@pytest.fixture
def console_only():
    """A model the app does not route, resolvable by name all the same: the
    console registers the metadata of its models alongside the app's."""
    from fastedgy.metadata_model import MetadataModelRegistry
    from fastedgy.test.models import FsoTag

    registry = get_service(MetadataModelRegistry)
    saved = {name: copy.copy(value) for name, value in vars(registry).items()}
    registry.register_model(FsoTag)

    yield FsoTag

    vars(registry).update(saved)


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


async def test_a_model_the_app_does_not_route_is_refused(agent, console_only):
    tag = await console_only(name="Seeded").save()

    for tool, arguments in (
        ("list_records", {}),
        ("get_record", {"id": tag.id}),
        ("create_record", {"values": {"name": "Via MCP"}}),
        ("update_record", {"id": tag.id, "values": {"name": "Renamed"}}),
        ("delete_record", {"id": tag.id}),
    ):
        result = (await _call(agent, tool, model="fso_tag", **arguments))["result"]

        assert result["isError"] is True, tool
        assert "HTTP 405" in result["content"][0]["text"], tool

    assert [row.name for row in await console_only.query.all()] == ["Seeded"]


async def test_a_tool_whose_route_is_on_still_answers(agent):
    from fastedgy.test.models.comment import Comment

    comment = Comment(content="Seeded")
    await comment.save()

    assert payload(await _call(agent, "get_record", id=comment.id))["content"] == "Seeded"
    assert payload(await _call(agent, "list_records"))["total"] == 1
