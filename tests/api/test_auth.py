# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import BackgroundTasks
from jose import jwt

import fastedgy.api.auth as auth_api
from fastedgy import dependencies
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.depends import security
from fastedgy.depends.security import create_access_token, create_refresh_token, token_claims
from fastedgy.mail import Mail, MockAdapter
from fastedgy.orm import drain_signal_side_effects
from fastedgy.orm.filter import R
from fastedgy.realtime.broadcaster import WebSocketBroadcaster
from fastedgy.realtime.revocation import watch_revocations
from fastedgy.schemas.auth import ChangePasswordRequest, ForgotPasswordRequest
from fastedgy.test.factories import auth_token, create_user, hashed_password, use_request
from fastedgy.test.models.user import User

PASSWORD = "correct-horse"

LEGACY_HASH = "$2b$12$0GnN9bwwrzSImYer4BiNu.izB7eAJnt2uzkCAj5lFelyFM3.LlpKi"


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


async def _reset(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    await client.post("/api/auth/password/forgot", json={"email": email})
    user = await User.query.filter(email=email).first()
    assert user is not None

    return await client.post("/api/auth/password/reset", json={"token": user.reset_pwd_token, "password": password})


async def _protected(client: httpx.AsyncClient, access_token: str) -> int:
    return (await client.get("/api/users", params={"limit": 0}, headers=_auth_headers(access_token))).status_code


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _mailbox() -> MockAdapter:
    adapter = get_service(Mail).adapter
    assert isinstance(adapter, MockAdapter)
    adapter.clear()

    return adapter


def _claims(token: str) -> dict[str, Any]:
    settings = get_service(BaseSettings)

    return jwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])


def _legacy_refresh_token(email: str) -> str:
    settings = get_service(BaseSettings)
    claims = {"sub": email, "type": "refresh", "exp": datetime.now(UTC) + timedelta(days=3)}

    return jwt.encode(claims, settings.auth_secret_key, algorithm=settings.auth_algorithm)


def _renaming_while_hashing(monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    hash_password_async = auth_api.hash_password_async

    async def renamed_meanwhile(password: str) -> str:
        await User.global_query.filter(R("email", "=", email)).update(name="Renamed meanwhile")

        return await hash_password_async(password)

    monkeypatch.setattr(auth_api, "hash_password_async", renamed_meanwhile)


async def _name_of(email: str) -> str | None:
    return (await User.global_query.filter(R("email", "=", email)).get()).name


def _rechecks(monkeypatch: pytest.MonkeyPatch) -> list[list[int]]:
    watch_revocations()
    rechecked: list[list[int]] = []

    async def recheck(user_ids: Any) -> None:
        rechecked.append(list(user_ids))

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "recheck_users", recheck)

    return rechecked


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


async def test_forgot_password_answers_an_unknown_email_like_a_known_one(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "heidi@example.io")
    mailbox = _mailbox()

    known = await setup_http.post("/api/auth/password/forgot", json={"email": "heidi@example.io"})
    unknown = await setup_http.post("/api/auth/password/forgot", json={"email": "ghost@example.io"})

    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    assert mailbox.was_sent_to("heidi@example.io")
    assert not mailbox.was_sent_to("ghost@example.io")


async def test_forgot_password_does_not_tell_a_mail_that_failed(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register(setup_http, "heidi@example.io")

    async def failing(*args, **kwargs) -> None:
        raise ConnectionError("SMTP is down")

    monkeypatch.setattr(get_service(Mail), "send_template", failing)

    response = await setup_http.post("/api/auth/password/forgot", json={"email": "heidi@example.io"})

    assert response.status_code == 200


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


async def test_a_password_shorter_than_the_minimum_is_refused_everywhere(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_password_min_length=8)

    assert (await _register(setup_http, "judy@example.io", "1234567")).status_code == 422
    assert (await _register(setup_http, "judy@example.io", "12345678")).status_code == 200

    access_token = (await _login(setup_http, "judy@example.io", "12345678")).json()["access_token"]

    assert (await _change(setup_http, access_token, "12345678", "")).status_code == 422
    assert (await _reset(setup_http, "judy@example.io", "1")).status_code == 422
    assert (await _login(setup_http, "judy@example.io", "12345678")).status_code == 200

    override_settings(auth_password_min_length=4)

    assert (await _register(setup_http, "kim@example.io", "1234")).status_code == 200


async def test_by_default_a_password_of_any_length_is_accepted(setup_http: httpx.AsyncClient) -> None:
    assert (await _register(setup_http, "vera@example.io", "123456")).status_code == 200

    access_token = (await _login(setup_http, "vera@example.io", "123456")).json()["access_token"]

    assert (await _change(setup_http, access_token, "123456", "654321")).status_code == 200
    assert (await _reset(setup_http, "vera@example.io", "abcdef")).status_code == 200


def test_a_password_checked_outside_an_application_reads_no_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_settings(key: Any) -> Any:
        raise AssertionError(f"{key} read")

    monkeypatch.setattr(dependencies, "has_service", lambda key: False)
    monkeypatch.setattr(dependencies, "get_service", no_settings)

    assert ChangePasswordRequest(current_password="old", new_password="1").new_password == "1"


async def test_changing_the_password_revokes_the_tokens_issued_before(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    await _register(setup_http, "liam@example.io")
    before = (await _login(setup_http, "liam@example.io")).json()

    changed = await _change(setup_http, before["access_token"], PASSWORD, "updated-horse")

    assert changed.status_code == 200
    assert await _protected(setup_http, before["access_token"]) == 401
    assert (await _refresh(setup_http, before["refresh_token"])).status_code == 401
    assert await _protected(setup_http, changed.json()["access_token"]) == 200
    assert (await _refresh(setup_http, changed.json()["refresh_token"])).status_code == 200


async def test_resetting_the_password_revokes_the_tokens_issued_before(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    await _register(setup_http, "mia@example.io")
    before = (await _login(setup_http, "mia@example.io")).json()

    assert (await _reset(setup_http, "mia@example.io", "rotated-horse")).status_code == 200
    assert await _protected(setup_http, before["access_token"]) == 401
    assert (await _refresh(setup_http, before["refresh_token"])).status_code == 401


async def test_a_token_issued_before_the_fingerprint_stays_valid_until_it_expires(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    await _register(setup_http, "noah@example.io")
    current = (await _login(setup_http, "noah@example.io")).json()
    legacy_access = create_access_token({"sub": "noah@example.io"})
    legacy_refresh = _legacy_refresh_token("noah@example.io")

    assert (await _change(setup_http, current["access_token"], PASSWORD, "updated-horse")).status_code == 200
    assert await _protected(setup_http, legacy_access) == 200

    refreshed = await _refresh(setup_http, legacy_refresh)

    assert refreshed.status_code == 200
    assert await _protected(setup_http, refreshed.json()["access_token"]) == 200


async def test_refreshing_a_token_issued_before_the_fingerprint_never_extends_it(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    await _register(setup_http, "nina@example.io")
    current = (await _login(setup_http, "nina@example.io")).json()
    stolen = _legacy_refresh_token("nina@example.io")

    assert (await _change(setup_http, current["access_token"], PASSWORD, "updated-horse")).status_code == 200

    pair = (await _refresh(setup_http, stolen)).json()

    for token in (pair["access_token"], pair["refresh_token"]):
        assert "pwf" not in _claims(token)

    assert _claims(pair["refresh_token"])["exp"] == _claims(stolen)["exp"]

    rotated = (await _refresh(setup_http, pair["refresh_token"])).json()

    assert _claims(rotated["refresh_token"])["exp"] == _claims(stolen)["exp"]


async def test_by_default_a_password_change_ends_no_session(setup_http: httpx.AsyncClient) -> None:
    await _register(setup_http, "olga@example.io")
    before = (await _login(setup_http, "olga@example.io")).json()

    assert "pwf" not in _claims(before["access_token"])
    assert (await _change(setup_http, before["access_token"], PASSWORD, "updated-horse")).status_code == 200
    assert await _protected(setup_http, before["access_token"]) == 200
    assert await _protected(setup_http, create_access_token({"sub": "olga@example.io", "pwf": "stale"})) == 200
    assert (await _refresh(setup_http, before["refresh_token"])).status_code == 200

    legacy_refresh = _legacy_refresh_token("olga@example.io")
    renewed = (await _refresh(setup_http, legacy_refresh)).json()

    assert "pwf" not in _claims(renewed["access_token"])
    assert _claims(renewed["refresh_token"])["exp"] > _claims(legacy_refresh)["exp"]


async def test_by_default_a_password_change_has_no_socket_checked_again(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register(setup_http, "vic@example.io")
    access_token = (await _login(setup_http, "vic@example.io")).json()["access_token"]
    rechecked = _rechecks(monkeypatch)

    await _change(setup_http, access_token, PASSWORD, "updated-horse")
    await drain_signal_side_effects()

    assert rechecked == []


async def test_a_login_that_upgrades_a_bcrypt_hash_hands_out_working_tokens(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    user = await create_user(email="legacy@example.io", password=LEGACY_HASH)
    legacy_access = create_access_token({"sub": "legacy@example.io"})
    refreshed_on_bcrypt = create_refresh_token(token_claims(user))

    tokens = (await _login(setup_http, "legacy@example.io", "secret")).json()
    upgraded = await User.query.filter(email="legacy@example.io").first()

    assert upgraded is not None and upgraded.password and upgraded.password.startswith("$argon2id$")
    assert await _protected(setup_http, tokens["access_token"]) == 200
    assert (await _refresh(setup_http, tokens["refresh_token"])).status_code == 200
    assert await _protected(setup_http, legacy_access) == 200
    assert (await _refresh(setup_http, refreshed_on_bcrypt)).status_code == 401


async def test_emails_are_matched_regardless_of_case(setup_http: httpx.AsyncClient) -> None:
    assert (await _register(setup_http, "Jean.Dupont@Example.io")).status_code == 200
    assert (await _register(setup_http, "jean.dupont@example.io")).status_code == 400
    assert (await _login(setup_http, "JEAN.DUPONT@example.io")).status_code == 200

    mailbox = _mailbox()

    assert (await setup_http.post("/api/auth/password/forgot", json={"email": "jean.dupont@example.io"})).is_success
    assert mailbox.was_sent_to("Jean.Dupont@example.io")


async def test_two_accounts_differing_only_by_case_are_told_apart_by_exact_match(
    setup_http: httpx.AsyncClient,
) -> None:
    await create_user(email="Jean@example.io", password=PASSWORD)
    await create_user(email="jean@example.io", password="other-horse")
    mailbox = _mailbox()

    assert (await _login(setup_http, "Jean@example.io")).status_code == 200
    assert (await _login(setup_http, "jean@example.io", "other-horse")).status_code == 200
    assert (await _login(setup_http, "JEAN@example.io")).status_code == 401
    assert (await setup_http.post("/api/auth/password/forgot", json={"email": "JEAN@example.io"})).is_success
    assert mailbox.sent == []


async def test_a_short_password_is_refused_with_a_plain_message(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_password_min_length=8)
    response = await _register(setup_http, "sam@example.io", "short")
    error = response.json()["detail"][0]

    assert response.status_code == 422
    assert error["type"] == "password_too_short"
    assert error["msg"] == "Password must be at least 8 characters"


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


async def test_forgot_password_looks_nothing_up_before_it_answers(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    looked_up: list[str] = []

    async def find(identifier: str) -> None:
        looked_up.append(identifier)

    monkeypatch.setattr(auth_api, "find_user", find)
    tasks = BackgroundTasks()

    with use_request(locale="en"):
        answer = await auth_api.password_forgot(
            ForgotPasswordRequest(email="ghost@example.io"), tasks, get_service(BaseSettings), get_service(Mail)
        )

    assert answer.message == "Password reset email sent"
    assert looked_up == []

    await tasks()

    assert looked_up == ["ghost@example.io"]


async def test_a_forgot_that_read_the_account_before_a_password_change_keeps_the_new_password(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    await _register(setup_http, "paul@example.io")
    victim = (await _login(setup_http, "paul@example.io")).json()
    thief = (await _login(setup_http, "paul@example.io")).json()
    stale = await User.global_query.filter(R("email", "=", "paul@example.io")).get()

    async def read_before_the_change(identifier: str) -> User:
        return stale

    changed = await _change(setup_http, victim["access_token"], PASSWORD, "updated-horse")
    monkeypatch.setattr(auth_api, "find_user", read_before_the_change)
    await setup_http.post("/api/auth/password/forgot", json={"email": "paul@example.io"})

    assert (await _login(setup_http, "paul@example.io")).status_code == 401
    assert (await _login(setup_http, "paul@example.io", "updated-horse")).status_code == 200
    assert await _protected(setup_http, thief["access_token"]) == 401
    assert await _protected(setup_http, changed.json()["access_token"]) == 200


async def test_changing_a_password_leaves_the_other_columns_as_the_row_holds_them(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register(setup_http, "quinn@example.io")
    access_token = (await _login(setup_http, "quinn@example.io")).json()["access_token"]
    _renaming_while_hashing(monkeypatch, "quinn@example.io")

    assert (await _change(setup_http, access_token, PASSWORD, "updated-horse")).status_code == 200
    assert await _name_of("quinn@example.io") == "Renamed meanwhile"


async def test_resetting_a_password_leaves_the_other_columns_as_the_row_holds_them(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register(setup_http, "ruth@example.io")
    await setup_http.post("/api/auth/password/forgot", json={"email": "ruth@example.io"})
    token = (await User.global_query.filter(R("email", "=", "ruth@example.io")).get()).reset_pwd_token
    _renaming_while_hashing(monkeypatch, "ruth@example.io")

    reset = {"token": token, "password": "rotated-horse"}

    assert (await setup_http.post("/api/auth/password/reset", json=reset)).status_code == 200
    assert await _name_of("ruth@example.io") == "Renamed meanwhile"
    assert (await _login(setup_http, "ruth@example.io", "rotated-horse")).status_code == 200
    assert (await setup_http.post("/api/auth/password/reset", json=reset)).status_code == 400


async def test_a_forgot_request_has_no_socket_checked_again(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    await _register(setup_http, "uma@example.io")
    access_token = (await _login(setup_http, "uma@example.io")).json()["access_token"]
    rechecked = _rechecks(monkeypatch)

    await setup_http.post("/api/auth/password/forgot", json={"email": "uma@example.io"})
    await drain_signal_side_effects()

    assert rechecked == []

    await _change(setup_http, access_token, PASSWORD, "updated-horse")
    await drain_signal_side_effects()

    assert len(rechecked) == 1


async def test_the_test_kit_token_is_revoked_by_a_password_change(
    setup_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_revoke_tokens_on_password_change=True)
    user = await create_user(email="tess@example.io", password=PASSWORD)
    token = auth_token(user)

    assert await _protected(setup_http, token) == 200

    await user.save(values={"password": hashed_password("updated-horse")})

    assert await _protected(setup_http, token) == 401
