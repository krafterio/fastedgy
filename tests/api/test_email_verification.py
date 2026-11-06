# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from jose import jwt

from fastedgy.api.auth import OnEmailVerifiedEvent, send_email_verification
from fastedgy.bus import Bus
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.depends.security import create_email_verification_token
from fastedgy.mail import Mail, MockAdapter
from fastedgy.test.factories import create_user, use_request
from fastedgy.test.models.user import User


async def _verify(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post("/api/auth/email/verify", json={"token": token})


async def _verified_at(user: User) -> datetime | None:
    await user.load()

    return user.email_verified_at


async def test_a_verification_token_marks_the_email_verified(setup_http: httpx.AsyncClient) -> None:
    user = await create_user(email="alice@example.io")

    response = await _verify(setup_http, create_email_verification_token(user))

    assert response.status_code == 200
    assert await _verified_at(user) is not None


async def test_a_verification_token_names_the_email_it_was_sent_to(setup_http: httpx.AsyncClient) -> None:
    user = await create_user(email="alice@example.io")
    token = create_email_verification_token(user)
    await user.save(values={"email": "renamed@example.io"})

    response = await _verify(setup_http, token)

    assert response.status_code == 400
    assert await _verified_at(user) is None


async def test_an_expired_verification_token_is_refused(setup_http: httpx.AsyncClient) -> None:
    user = await create_user(email="alice@example.io")

    response = await _verify(setup_http, create_email_verification_token(user, timedelta(seconds=-1)))

    assert response.status_code == 400
    assert await _verified_at(user) is None


async def test_a_token_of_another_type_does_not_verify(setup_http: httpx.AsyncClient) -> None:
    settings = get_service(BaseSettings)
    user = await create_user(email="alice@example.io")
    claims = {"uid": user.id, "email": user.email, "type": "access", "exp": datetime.now(UTC) + timedelta(days=1)}

    response = await _verify(setup_http, jwt.encode(claims, settings.auth_secret_key, settings.auth_algorithm))

    assert response.status_code == 400
    assert await _verified_at(user) is None


async def test_a_password_reset_marks_the_email_verified(setup_http: httpx.AsyncClient) -> None:
    user = await create_user(email="alice@example.io")
    await user.save(
        values={"reset_pwd_token": "reset-token", "reset_pwd_expires_at": datetime.now(UTC) + timedelta(hours=1)}
    )

    response = await setup_http.post(
        "/api/auth/password/reset", json={"token": "reset-token", "password": "new-correct-horse"}
    )

    assert response.status_code == 200, response.text
    assert await _verified_at(user) is not None


async def test_the_verification_email_carries_a_working_link(setup_http: httpx.AsyncClient) -> None:
    mail = get_service(Mail)
    adapter = mail.adapter
    assert isinstance(adapter, MockAdapter)
    adapter.clear()
    user = await create_user(email="alice@example.io")

    with use_request(locale="fr"):
        await send_email_verification(user, mail, "https://app.example.io", locale="en")

    assert len(adapter.sent) == 1
    body = adapter.sent[0].get_body(("html",))
    assert body is not None
    content = body.get_content()
    token = content.split("/email/verify?token=")[1].split('"')[0]
    assert (await _verify(setup_http, token)).status_code == 200


def _verified_events(monkeypatch: pytest.MonkeyPatch) -> list[OnEmailVerifiedEvent]:
    bus = get_service(Bus)
    dispatch = bus.dispatch
    events: list[OnEmailVerifiedEvent] = []

    async def record(event, *args, **kwargs):
        if isinstance(event, OnEmailVerifiedEvent):
            events.append(event)

        return await dispatch(event, *args, **kwargs)

    monkeypatch.setattr(bus, "dispatch", record)

    return events


async def test_a_first_verification_dispatches_the_verified_event_once(
    setup_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = _verified_events(monkeypatch)
    user = await create_user(email="alice@example.io")
    token = create_email_verification_token(user)

    await _verify(setup_http, token)
    await _verify(setup_http, token)

    assert [event.user.id for event in events] == [user.id]
