# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The `override_settings` fixture, and the isolation it owes the next test."""

from collections.abc import Callable

import pytest

from fastedgy.app import FastEdgy
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service


async def test_override_reaches_the_settings_service(
    setup_db: FastEdgy, override_settings: Callable[..., None]
) -> None:
    override_settings(auth_secret_key="overridden-for-this-test")

    assert get_service(BaseSettings).auth_secret_key == "overridden-for-this-test"


async def test_the_override_does_not_leak_to_the_next_test(setup_db: FastEdgy) -> None:
    assert get_service(BaseSettings).auth_secret_key != "overridden-for-this-test"


async def test_an_unknown_setting_is_refused(setup_db: FastEdgy, override_settings: Callable[..., None]) -> None:
    with pytest.raises(AttributeError):
        override_settings(nonexistent_setting="x")
