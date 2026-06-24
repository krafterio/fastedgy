# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Factories and auth helpers shared by the test suite.

These helpers create records through the ORM so they work both for API tests
(seed data, then authenticate as a chosen user) and for pure database/ORM tests
that never touch the HTTP layer.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import httpx

from fastedgy import context
from fastedgy.http import Request


def make_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    """Build a minimal ASGI request usable to drive the context in tests."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": headers or [],
        }
    )


@contextmanager
def use_request(*, locale: str | None = None, timezone: str | None = None, user: Any = None) -> Generator[Request]:
    """Run a block within a request context, optionally seeding locale/timezone/user."""
    request = make_request()
    token = context.set_request(request)

    try:
        if locale is not None:
            context.set_locale(locale)

        if timezone is not None:
            context.set_timezone(timezone)

        if user is not None:
            context.set_user(user)

        yield request
    finally:
        context.reset_request(token)


async def create_user(
    email: str = "user@example.io",
    name: str | None = "John Doe",
    password: str = "secret",
    **extra,
):
    """Create and persist a User through the ORM (the dedicated user flow)."""
    from fastedgy.test.models.user import User

    user = User(email=email, name=name, password=password, **extra)
    await user.save()

    return user


async def create_workspace(slug: str = "acme", name: str | None = None, **extra):
    from fastedgy.test.models.workspace import Workspace

    workspace = Workspace(slug=slug, name=name, **extra)
    await workspace.save()

    return workspace


async def create_category(name: str = "Books", **extra):
    from fastedgy.test.models.category import Category

    category = Category(name=name, **extra)
    await category.save()

    return category


async def create_tag(name: str = "tag", **extra):
    from fastedgy.test.models.tag import Tag

    tag = Tag(name=name, **extra)
    await tag.save()

    return tag


async def create_product(name: str = "Laptop", price: str = "999.00", **extra):
    from fastedgy.test.models.product import Product

    product = Product(name=name, price=price, **extra)
    await product.save()

    return product


def auth_token(user) -> str:
    """Mint an access token for an existing user (selects it by its email)."""
    from fastedgy.depends.security import create_access_token

    return create_access_token({"sub": user.email})


def authenticate(client: httpx.AsyncClient, user) -> httpx.AsyncClient:
    """Authenticate an HTTP client as the given user for subsequent requests."""
    client.headers["Authorization"] = f"Bearer {auth_token(user)}"

    return client


__all__ = [
    "make_request",
    "use_request",
    "create_user",
    "create_workspace",
    "create_category",
    "create_tag",
    "create_product",
    "auth_token",
    "authenticate",
]
