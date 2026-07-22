# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Membership routes: the ``workspace``/``user`` foreign keys are read_only —
a membership is created and linked in code (``apply_readonly_values``), never
through the API, and can never be re-pointed."""

import httpx
import pytest

from fastedgy.test.factories import create_user


async def _make_workspace(client: httpx.AsyncClient, slug: str = "acme") -> dict:
    return (await client.post("/api/workspaces", json={"slug": slug})).json()


async def _make_membership(workspace_id: int, user_id: int | None):
    from fastedgy.test.models.workspace_user import WorkspaceUser

    membership = WorkspaceUser(workspace=workspace_id, user=user_id)
    membership.apply_readonly_values({"workspace": workspace_id, "user": user_id})
    await membership.save()

    return membership


# --- create -----------------------------------------------------------------


async def test_api_cannot_create_a_membership(auth_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(auth_http)
    user = await create_user()

    response = await auth_http.post(
        "/api/workspace_users",
        json={"workspace": workspace["id"], "user": user.id},
    )

    assert response.status_code == 422


async def test_code_creates_membership_with_readonly_values(auth_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(auth_http)
    user = await create_user()

    membership = await _make_membership(workspace["id"], user.id)

    response = await auth_http.get(f"/api/workspace_users/{membership.id}")

    assert response.status_code == 200
    assert response.json()["workspace"] == {"id": workspace["id"]}
    assert response.json()["user"] == {"id": user.id}


async def test_api_cannot_repoint_a_membership(auth_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(auth_http)
    user = await create_user()
    other = await create_user(email="other@example.io")
    membership = await _make_membership(workspace["id"], user.id)

    response = await auth_http.patch(
        f"/api/workspace_users/{membership.id}",
        json={"user": other.id},
    )

    assert response.status_code == 200
    fetched = await auth_http.get(f"/api/workspace_users/{membership.id}")
    assert fetched.json()["user"] == {"id": user.id}


async def test_duplicate_pair_is_rejected(auth_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(auth_http)
    user = await create_user()

    await _make_membership(workspace["id"], user.id)

    with pytest.raises(Exception, match="(?i)unique|duplicate"):
        await _make_membership(workspace["id"], user.id)


# --- get / delete -----------------------------------------------------------


async def test_get_returns_membership(auth_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(auth_http)
    user = await create_user()
    membership = await _make_membership(workspace["id"], user.id)

    response = await auth_http.get(f"/api/workspace_users/{membership.id}")

    assert response.status_code == 200
    assert response.json()["id"] == membership.id


async def test_delete_removes_membership(auth_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(auth_http)
    user = await create_user()
    membership = await _make_membership(workspace["id"], user.id)

    response = await auth_http.delete(f"/api/workspace_users/{membership.id}")

    assert response.status_code in (200, 204)
    assert (await auth_http.get(f"/api/workspace_users/{membership.id}")).status_code == 404
