# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from jose import jwt

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.depends.security import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_workspace,
    hash_password,
    verify_password,
)
from fastedgy.http import Request
from fastedgy.test.factories import create_user, create_workspace
from fastedgy.test.models.workspace_user import WorkspaceUser


def test_hash_and_verify_password() -> None:
    hashed = hash_password("secret")

    assert hashed != "secret"
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "secret") is True
    assert verify_password(hashed, "wrong") is False
    assert verify_password("", "secret") is False
    assert verify_password(hashed, "") is False


def test_a_bcrypt_hash_is_flagged_for_an_upgrade() -> None:
    """What lets a base migrate off bcrypt without a password reset: the stored
    hash names its own scheme, and a login on an older one can rehash in place.
    """
    from fastedgy.depends.hasher import get_hasher_registry

    registry = get_hasher_registry()
    legacy_hash = "$2b$12$0GnN9bwwrzSImYer4BiNu.izB7eAJnt2uzkCAj5lFelyFM3.LlpKi"

    assert registry.is_hashed(legacy_hash)
    assert registry.needs_rehash(legacy_hash)
    assert not registry.needs_rehash(hash_password("secret"))
    assert not registry.is_hashed("secret")


def test_verify_password_accepts_a_preexisting_bcrypt_hash() -> None:
    # A hash produced before the passlib-to-bcrypt switch must still verify.
    legacy_hash = "$2b$12$0GnN9bwwrzSImYer4BiNu.izB7eAJnt2uzkCAj5lFelyFM3.LlpKi"

    assert verify_password(legacy_hash, "secret") is True
    assert verify_password(legacy_hash, "wrong") is False


def test_verify_password_rejects_a_malformed_hash() -> None:
    assert verify_password("not-a-bcrypt-hash", "secret") is False


def test_hash_password_handles_passwords_longer_than_72_bytes() -> None:
    long_password = "a" * 100

    hashed = hash_password(long_password)

    assert verify_password(hashed, long_password) is True


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


async def test_current_workspace_comes_from_the_membership_join(setup_db: FastEdgy) -> None:
    user = await create_user(email="ada@example.io")
    workspace = await create_workspace(slug="acme", name="Acme")
    await WorkspaceUser(user=user, workspace=workspace).save()

    # The tenant context lives on the request, so the assertions below run while
    # it is still the current one.
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/acme/products",
            "query_string": b"",
            "headers": [],
            "path_params": {"workspace": "acme"},
        }
    )
    token = context.set_request(request)

    try:
        resolved = await get_current_workspace(current_user=user)

        assert resolved is not None
        assert resolved.slug == "acme"
        # The join carries the row: reading it back by id was a second query on
        # the tenant, paid once per request of every session.
        assert resolved is getattr(context.get_workspace_user(), "workspace", None)
    finally:
        context.reset_request(token)


async def test_an_unhashed_password_is_repaired_outside_strict_mode(setup_db: FastEdgy) -> None:
    """Production keeps working rather than failing a signup, but never stores
    the clear value, and says loudly that a call site has to be fixed.
    """
    from fastedgy.config import BaseSettings
    from fastedgy.depends.hasher import get_hasher_registry
    from fastedgy.test.models.user import User

    settings = get_service(BaseSettings)
    settings.strict_password_hash = False

    try:
        user = User(email="lenient@example.io", name="Lenient", password="secret")
        await user.save()
    finally:
        settings.strict_password_hash = True

    stored = await User.query.get(email="lenient@example.io")

    assert stored.password != "secret"
    assert get_hasher_registry().is_hashed(stored.password)
    assert verify_password(stored.password, "secret") is True


async def test_an_unhashed_password_raises_in_strict_mode(setup_db: FastEdgy) -> None:
    import pytest

    from fastedgy.test.models.user import User

    with pytest.raises(ValueError, match="not a password hash"):
        await User(email="strict@example.io", name="Strict", password="secret").save()
