# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
import pytest

from fastedgy.dependencies import get_service
from fastedgy.depends import security
from fastedgy.mail import Mail, MockAdapter
from fastedgy.test.models.user import User

PASSWORD = "correct-horse"


async def _register(
    client: httpx.AsyncClient,
    email: str,
    password: str = PASSWORD,
    name: str = "Jane",
) -> httpx.Response:
    return await client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


async def _login(client: httpx.AsyncClient, username: str, password: str = PASSWORD) -> httpx.Response:
    return await client.post("/api/auth/token", json={"username": username, "password": password})


async def _refresh(client: httpx.AsyncClient, refresh_token: str) -> httpx.Response:
    return await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})


async def _change(client: httpx.AsyncClient, access_token: str, current: str, new: str) -> httpx.Response:
    return await client.post(
        "/api/auth/password/change",
        json={"current_password": current, "new_password": new},
        headers=_auth_headers(access_token),
    )


async def _protected(client: httpx.AsyncClient, access_token: str) -> int:
    return (await client.get("/api/users", params={"limit": 0}, headers=_auth_headers(access_token))).status_code


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _mailbox() -> MockAdapter:
    adapter = get_service(Mail).adapter
    assert isinstance(adapter, MockAdapter)
    adapter.clear()

    return adapter


async def test_register_then_login_returns_tokens(setup_http: httpx.AsyncClient) -> None:
    assert (await _register(setup_http, "alice@example.io")).status_code == 200

    response = await _login(setup_http, "alice@example.io")

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
    assert (await _login(setup_http, "ghost@example.io")).status_code == 401


async def test_refresh_token_issues_a_new_access_token(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "dave@example.io")
    tokens = (await _login(setup_http, "dave@example.io")).json()

    response = await _refresh(setup_http, tokens["refresh_token"])

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_with_invalid_token_is_rejected(setup_http: httpx.AsyncClient) -> None:
    assert (await _refresh(setup_http, "nope")).status_code == 401


async def test_access_token_grants_access_to_protected_routes(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "erin@example.io")
    access_token = (await _login(setup_http, "erin@example.io")).json()["access_token"]

    assert await _protected(setup_http, access_token) == 200
    assert await _protected(setup_http, "nope") == 401


async def test_change_password(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "frank@example.io")
    access_token = (await _login(setup_http, "frank@example.io")).json()["access_token"]

    response = await _change(setup_http, access_token, PASSWORD, "updated-horse")

    assert response.status_code == 200
    assert (await _login(setup_http, "frank@example.io", "updated-horse")).status_code == 200


async def test_change_password_with_wrong_current_is_rejected(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "grace@example.io")
    access_token = (await _login(setup_http, "grace@example.io")).json()["access_token"]

    assert (await _change(setup_http, access_token, "wrong", "updated-horse")).status_code == 400


async def test_forgot_password_sends_a_recovery_email(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "heidi@example.io")
    mailbox = _mailbox()

    response = await setup_http.post("/api/auth/password/forgot", json={"email": "heidi@example.io"})

    assert response.status_code == 200
    assert mailbox.was_sent_to("heidi@example.io")


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

    reset = await setup_http.post("/api/auth/password/reset", json={"token": token, "password": "rotated-horse"})
    assert reset.status_code == 200

    assert (await _login(setup_http, "ivan@example.io", "rotated-horse")).status_code == 200


async def test_a_login_naming_no_account_checks_a_password_all_the_same(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register(setup_http, "rose@example.io")
    checked: list[str | None] = []
    verify_password = security.verify_password

    def counting(password: str | None, candidate: str | None) -> bool:
        checked.append(candidate)

        return verify_password(password, candidate)

    monkeypatch.setattr(security, "verify_password", counting)

    assert (await _login(setup_http, "rose@example.io", "wrong-horse")).status_code == 401
    assert (await _login(setup_http, "ghost@example.io", "wrong-horse")).status_code == 401
    assert checked == ["wrong-horse", "wrong-horse"]
