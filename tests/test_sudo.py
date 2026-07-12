# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.sudo import SudoChecker
from fastedgy.test.factories import create_user, use_request


async def test_sudo_denies_by_default(setup_db: FastEdgy) -> None:
    checker = get_service(SudoChecker)

    assert await checker.is_sudo() is False

    user = await create_user(email="anyone@example.io")

    with use_request(user=user):
        assert await checker.is_sudo() is False
