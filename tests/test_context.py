# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from zoneinfo import ZoneInfo

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.http import Request
from fastedgy.test.factories import create_user


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
    )


def test_request_context_is_set_and_reset() -> None:
    token = context.set_request(_request())

    assert context.get_request() is not None

    context.reset_request(token)

    assert context.get_request() is None


async def test_user_context(setup_db: FastEdgy) -> None:
    user = await create_user(email="ctx@example.io")
    token = context.set_request(_request())

    try:
        context.set_user(user)

        assert context.get_user() is user
    finally:
        context.reset_request(token)


def test_locale_and_timezone_context() -> None:
    token = context.set_request(_request())

    try:
        context.set_locale("fr")
        context.set_timezone("Europe/Paris")

        assert context.get_locale() == "fr"
        assert context.get_timezone() == ZoneInfo("Europe/Paris")
    finally:
        context.reset_request(token)
