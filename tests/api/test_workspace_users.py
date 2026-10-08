# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

import httpx

from fastedgy.test.factories import authenticate, create_user, create_workspace, create_workspace_user


async def _two_workspaces():
    acme = await create_workspace(slug="acme", name="Acme")
    other = await create_workspace(slug="other", name="Other")
    me = await create_user(email="me@example.io")
    colleague = await create_user(email="colleague@example.io")
    stranger = await create_user(email="stranger@example.io")

    await create_workspace_user(me, acme)
    await create_workspace_user(colleague, acme)
    await create_workspace_user(stranger, other)

    return me, colleague, stranger


async def test_lists_the_members_of_the_workspace_only(setup_http: httpx.AsyncClient) -> None:
    me, colleague, _stranger = await _two_workspaces()
    client = authenticate(setup_http, me)

    response = await client.get("/api/acme/users", headers={"X-Fields": "id,email"})

    assert response.status_code == 200, response.text
    assert {item["id"] for item in response.json()["items"]} == {me.id, colleague.id}


async def test_filters_the_members_like_any_list(setup_http: httpx.AsyncClient) -> None:
    me, colleague, _stranger = await _two_workspaces()
    client = authenticate(setup_http, me)

    response = await client.get(
        "/api/acme/users",
        headers={"X-Fields": "id", "X-Filter": json.dumps(["email", "icontains", "COLLEAGUE"])},
    )

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [colleague.id]


async def test_reads_a_member_but_not_a_user_of_another_workspace(setup_http: httpx.AsyncClient) -> None:
    me, colleague, stranger = await _two_workspaces()
    client = authenticate(setup_http, me)

    assert (await client.get(f"/api/acme/users/{colleague.id}")).status_code == 200
    assert (await client.get(f"/api/acme/users/{stranger.id}")).status_code == 404


async def test_a_workspace_the_user_does_not_belong_to_is_not_found(setup_http: httpx.AsyncClient) -> None:
    me, _colleague, _stranger = await _two_workspaces()
    client = authenticate(setup_http, me)

    assert (await client.get("/api/other/users")).status_code == 404
