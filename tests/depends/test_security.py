# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from jose import jwt

from fastedgy.app import FastEdgy
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.depends.security import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from fastedgy.test.factories import create_user


def test_hash_and_verify_password() -> None:
    hashed = hash_password("secret")

    assert hashed != "secret"
    assert verify_password(hashed, "secret") is True
    assert verify_password(hashed, "wrong") is False
    assert verify_password("", "secret") is False


async def test_create_access_token_roundtrip(setup_db: FastEdgy) -> None:
    settings = get_service(BaseSettings)
    token = create_access_token({"sub": "user@example.io"})

    payload = jwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])

    assert payload["sub"] == "user@example.io"
    assert payload["type"] == "access"
    assert "exp" in payload


async def test_create_refresh_token_has_refresh_type(setup_db: FastEdgy) -> None:
    settings = get_service(BaseSettings)
    token = create_refresh_token({"sub": "user@example.io"})

    payload = jwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])

    assert payload["type"] == "refresh"


async def test_authenticate_user(setup_db: FastEdgy) -> None:
    user = await create_user(email="sec@example.io", password=hash_password("secret"))

    authenticated = await authenticate_user("sec@example.io", "secret")

    assert authenticated is not False
    assert authenticated.id == user.id
    assert await authenticate_user("sec@example.io", "wrong") is False
    assert await authenticate_user("nobody@example.io", "secret") is False
