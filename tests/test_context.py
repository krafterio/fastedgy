# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from zoneinfo import ZoneInfo

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.test.factories import create_user, make_request, use_request


def test_request_context_is_set_and_reset() -> None:
    token = context.set_request(make_request())

    assert context.get_request() is not None

    context.reset_request(token)

    assert context.get_request() is None


async def test_user_context(setup_db: FastEdgy) -> None:
    user = await create_user(email="ctx@example.io")

    with use_request(user=user):
        assert context.get_user() is user


def test_locale_and_timezone_context() -> None:
    with use_request(locale="fr", timezone="Europe/Paris"):
        assert context.get_locale() == "fr"
        assert context.get_timezone() == ZoneInfo("Europe/Paris")
