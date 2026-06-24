# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from ..helpers import seed_user


# Users are created through a dedicated registration flow, not the generic CRUD
# endpoint (`password` is excluded from the input model yet required), so these
# tests seed users via the ORM and exercise the read/update/delete actions.


# --- get --------------------------------------------------------------------


async def test_get_returns_seeded_user(setup_http: httpx.AsyncClient) -> None:
    user = await seed_user(email="john@example.io", name="John Doe")

    response = await setup_http.get(f"/api/users/{user.id}")

    assert response.status_code == 200

    item = response.json()

    assert item["email"] == "john@example.io"
    assert item["name"] == "John Doe"


async def test_get_unknown_user_returns_404(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.get("/api/users/999999")

    assert response.status_code == 404


async def test_password_and_secrets_are_excluded_from_output(setup_http: httpx.AsyncClient) -> None:
    user = await seed_user()

    item = (await setup_http.get(f"/api/users/{user.id}")).json()

    assert "password" not in item
    assert "reset_pwd_token" not in item
    assert "reset_pwd_expires_at" not in item


# --- list -------------------------------------------------------------------


async def test_list_returns_seeded_users(setup_http: httpx.AsyncClient) -> None:
    await seed_user(email="a@example.io", name="Alice")
    await seed_user(email="b@example.io", name="Bob")

    payload = (await setup_http.get("/api/users")).json()

    assert payload["total"] == 2
    assert {item["email"] for item in payload["items"]} == {"a@example.io", "b@example.io"}


# --- patch ------------------------------------------------------------------


async def test_patch_updates_name(setup_http: httpx.AsyncClient) -> None:
    user = await seed_user(email="john@example.io", name="John")

    response = await setup_http.patch(f"/api/users/{user.id}", json={"name": "Jonathan"})

    assert response.status_code == 200
    assert response.json()["name"] == "Jonathan"


# --- delete -----------------------------------------------------------------


async def test_delete_removes_user(setup_http: httpx.AsyncClient) -> None:
    user = await seed_user()

    response = await setup_http.delete(f"/api/users/{user.id}")

    assert response.status_code in (200, 204)
    assert (await setup_http.get(f"/api/users/{user.id}")).status_code == 404
