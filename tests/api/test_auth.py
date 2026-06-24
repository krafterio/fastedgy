# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from fastedgy.dependencies import get_service
from fastedgy.mail import Mail, MockAdapter
from fastedgy.test.models.user import User


async def _register(
    client: httpx.AsyncClient,
    email: str,
    password: str = "secret",
    name: str = "Jane",
) -> httpx.Response:
    return await client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


async def _login(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/token", json={"username": username, "password": password})


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def test_register_then_login_returns_tokens(setup_http: httpx.AsyncClient) -> None:
    assert (await _register(setup_http, "alice@example.io")).status_code == 200

    response = await _login(setup_http, "alice@example.io", "secret")

    assert response.status_code == 200

    body = response.json()

    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_register_duplicate_email_is_rejected(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "bob@example.io")

    assert (await _register(setup_http, "bob@example.io")).status_code == 400


async def test_login_with_wrong_password_is_rejected(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "carol@example.io")

    assert (await _login(setup_http, "carol@example.io", "wrong")).status_code == 401


async def test_login_unknown_user_is_rejected(setup_http: httpx.AsyncClient) -> None:
    assert (await _login(setup_http, "ghost@example.io", "secret")).status_code == 401


async def test_refresh_token_issues_a_new_access_token(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "dave@example.io")
    tokens = (await _login(setup_http, "dave@example.io", "secret")).json()

    response = await setup_http.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_with_invalid_token_is_rejected(setup_http: httpx.AsyncClient) -> None:
    assert (await setup_http.post("/api/auth/refresh", json={"refresh_token": "nope"})).status_code == 401


async def test_access_token_grants_access_to_protected_routes(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "erin@example.io")
    access_token = (await _login(setup_http, "erin@example.io", "secret")).json()["access_token"]

    response = await setup_http.get("/api/health", headers=_auth_headers(access_token))

    assert response.status_code == 200


async def test_change_password(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "frank@example.io")
    access_token = (await _login(setup_http, "frank@example.io", "secret")).json()["access_token"]

    response = await setup_http.post(
        "/api/auth/password/change",
        json={"current_password": "secret", "new_password": "updated"},
        headers=_auth_headers(access_token),
    )

    assert response.status_code == 200
    assert (await _login(setup_http, "frank@example.io", "updated")).status_code == 200


async def test_change_password_with_wrong_current_is_rejected(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "grace@example.io")
    access_token = (await _login(setup_http, "grace@example.io", "secret")).json()["access_token"]

    response = await setup_http.post(
        "/api/auth/password/change",
        json={"current_password": "wrong", "new_password": "updated"},
        headers=_auth_headers(access_token),
    )

    assert response.status_code == 400


async def test_forgot_password_sends_a_recovery_email(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "heidi@example.io")

    adapter = get_service(Mail).adapter
    assert isinstance(adapter, MockAdapter)
    adapter.clear()

    response = await setup_http.post("/api/auth/password/forgot", json={"email": "heidi@example.io"})

    assert response.status_code == 200
    assert adapter.was_sent_to("heidi@example.io")


async def test_forgot_password_with_unknown_email_is_rejected(setup_http: httpx.AsyncClient) -> None:
    assert (await setup_http.post("/api/auth/password/forgot", json={"email": "ghost@example.io"})).status_code == 400


async def test_password_reset_flow(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "ivan@example.io")
    await setup_http.post("/api/auth/password/forgot", json={"email": "ivan@example.io"})

    user = await User.query.filter(email="ivan@example.io").first()
    assert user is not None
    token = user.reset_pwd_token
    assert token

    validate = await setup_http.post("/api/auth/password/validate", json={"token": token})
    assert validate.status_code == 200
    assert validate.json()["valid"] is True

    reset = await setup_http.post("/api/auth/password/reset", json={"token": token, "password": "rotated"})
    assert reset.status_code == 200

    assert (await _login(setup_http, "ivan@example.io", "rotated")).status_code == 200
