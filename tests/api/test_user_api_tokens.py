# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Personal API keys: the secret exists once, in the creation response."""

import json

import httpx
import pytest

pytestmark = pytest.mark.anyio


async def _auth(email: str) -> dict[str, str]:
    """Headers of one identity: `authenticate` mutates the shared client, which
    two identities in the same test would trample."""
    from fastedgy.test.factories import auth_token, create_user

    return {"Authorization": f"Bearer {auth_token(await create_user(email=email))}"}


async def test_creation_returns_the_secret_once(setup_http: httpx.AsyncClient, setup_db):
    owner = await _auth("owner@example.io")
    created = (await setup_http.post("/api/user-api-tokens", json={"name": "Agent"}, headers=owner)).json()

    assert created["token"].startswith("fet_")
    assert created["token_hint"] == created["token"][:12]


async def test_listing_never_carries_the_secret_nor_its_hash(setup_http: httpx.AsyncClient, setup_db):
    owner = await _auth("owner@example.io")
    created = (await setup_http.post("/api/user-api-tokens", json={"name": "Agent"}, headers=owner)).json()

    response = await setup_http.get("/api/user-api-tokens", headers=owner)
    assert response.status_code == 200

    body = response.text
    assert created["token"] not in body
    assert "token_hash" not in body

    page = response.json()
    assert page["total"] == 1
    assert page["items"][0]["token_hint"] == created["token_hint"]
    assert "token_hash" not in page["items"][0]


async def test_listing_paginates_and_filters_like_any_model(setup_http: httpx.AsyncClient, setup_db):
    owner = await _auth("owner@example.io")

    for name in ("Agent", "Backup", "Cursor"):
        await setup_http.post("/api/user-api-tokens", json={"name": name}, headers=owner)

    page = (await setup_http.get("/api/user-api-tokens?limit=2&order_by=name:asc", headers=owner)).json()
    assert page["total"] == 3
    assert [item["name"] for item in page["items"]] == ["Agent", "Backup"]

    filtered = (
        await setup_http.get(
            "/api/user-api-tokens",
            headers={**owner, "X-Filter": json.dumps(["name", "ilike", "%urso%"])},
        )
    ).json()
    assert [item["name"] for item in filtered["items"]] == ["Cursor"]

    selected = (await setup_http.get("/api/user-api-tokens", headers={**owner, "X-Fields": "name"})).json()
    assert set(selected["items"][0]) == {"id", "name"}


async def test_a_key_is_listed_and_revoked_by_its_owner_only(setup_http: httpx.AsyncClient, setup_db):
    owner = await _auth("owner@example.io")
    stranger = await _auth("stranger@example.io")
    created = (await setup_http.post("/api/user-api-tokens", json={"name": "Agent"}, headers=owner)).json()

    assert (await setup_http.get("/api/user-api-tokens", headers=stranger)).json()["total"] == 0
    assert (await setup_http.delete(f"/api/user-api-tokens/{created['id']}", headers=stranger)).status_code == 404

    assert (await setup_http.delete(f"/api/user-api-tokens/{created['id']}", headers=owner)).status_code == 204
    assert (await setup_http.get("/api/user-api-tokens", headers=owner)).json()["total"] == 0


async def test_a_revoked_key_no_longer_authenticates(setup_http: httpx.AsyncClient, setup_db):
    owner = await _auth("owner@example.io")
    created = (await setup_http.post("/api/user-api-tokens", json={"name": "Agent"}, headers=owner)).json()
    await setup_http.delete(f"/api/user-api-tokens/{created['id']}", headers=owner)

    response = await setup_http.get("/api/user-api-tokens", headers={"X-Api-Token": created["token"]})

    assert response.status_code == 401


async def test_an_expired_key_no_longer_authenticates(setup_http: httpx.AsyncClient, setup_db):
    from datetime import UTC, datetime, timedelta

    owner = await _auth("owner@example.io")
    expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    created = (
        await setup_http.post("/api/user-api-tokens", json={"name": "Agent", "expires_at": expired}, headers=owner)
    ).json()

    response = await setup_http.get("/api/user-api-tokens", headers={"X-Api-Token": created["token"]})

    assert response.status_code == 401


async def test_the_model_is_registered_when_the_app_asks_for_it(setup_db):
    from fastedgy.models.user_api_token import find_user_api_token_model

    assert find_user_api_token_model() is not None


async def test_an_app_without_keys_answers_401_instead_of_crashing(
    setup_http: httpx.AsyncClient, setup_db, monkeypatch: pytest.MonkeyPatch
):
    """Without `FastEdgy(user_api_tokens=True)` no model is registered: a `fet_`
    bearer is then a credential nothing can resolve, not a 500."""
    import fastedgy.models.user_api_token as module

    monkeypatch.setattr(module, "find_user_api_token_model", lambda: None)
    response = await setup_http.get("/api/user-api-tokens", headers={"X-Api-Token": "fet_whatever"})

    assert response.status_code == 401


def test_asking_for_the_model_without_it_names_the_option(monkeypatch: pytest.MonkeyPatch):
    import fastedgy.models.user_api_token as module

    monkeypatch.setattr(module, "find_user_api_token_model", lambda: None)

    with pytest.raises(RuntimeError, match="user_api_tokens=True"):
        module.get_user_api_token_model()
