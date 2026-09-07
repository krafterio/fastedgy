# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The fields a workspace declares reach an agent the same way they reach the
web app: the MCP tools call the very actions the REST routes call, so entering
the workspace is what loads them on both paths."""

import pytest

from tests.mcp_server.helpers import payload, rpc

pytestmark = pytest.mark.anyio


async def _declare(workspace, name: str, field_type) -> None:
    from fastedgy.models.extra_field_model import WorkspaceExtraFieldModel
    from fastedgy.test.models.workspace_extra_field import WorkspaceExtraField

    field = WorkspaceExtraField(
        label=name.title(),
        name=name,
        field_type=field_type,
        model=WorkspaceExtraFieldModel.product,
        required=False,
    )
    field.workspace = workspace

    await field.save()


async def test_get_model_info_shows_the_fields_the_workspace_declared(agent, workspace_env) -> None:
    from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType

    client, token, slug = agent
    _, workspace = workspace_env
    await _declare(workspace, "priority", WorkspaceExtraFieldType.integer)

    info = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {"name": "get_model_info", "arguments": {"model": "product", "workspace": slug}},
        )
    )

    assert info["fields"]["extra_priority"]["extra"] is True
    assert info["fields"]["extra_priority"]["type"] == "integer"


async def test_an_agent_writes_and_reads_back_a_declared_extra_field(agent, workspace_env) -> None:
    from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType

    client, token, slug = agent
    _, workspace = workspace_env
    await _declare(workspace, "priority", WorkspaceExtraFieldType.integer)

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
                    "values": {"name": "Delta", "price": "4.00", "extra_priority": 7},
                    "fields": "id,name,extra_priority",
                },
            },
        )
    )

    assert created["extra_priority"] == 7

    listed = payload(
        await rpc(
            client,
            token,
            "tools/call",
            {
                "name": "list_records",
                "arguments": {
                    "model": "product",
                    "workspace": slug,
                    "fields": "name,extra_priority",
                    "filter": ["extra_priority", "=", 7],
                },
            },
        )
    )

    assert [item["name"] for item in listed["items"]] == ["Delta"]


async def test_an_undeclared_extra_field_is_refused(agent) -> None:
    client, token, slug = agent

    result = await rpc(
        client,
        token,
        "tools/call",
        {
            "name": "create_record",
            "arguments": {
                "model": "product",
                "workspace": slug,
                "values": {"name": "Epsilon", "price": "5.00", "extra_priority": 7},
            },
        },
    )

    assert result["result"]["isError"] is True
