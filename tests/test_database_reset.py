# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

from fastedgy.app import FastEdgy
from fastedgy.orm.transaction import run_signal_side_effect
from fastedgy.test.database import truncate_all_tables


async def test_emptying_the_database_waits_for_the_side_effects_still_running(setup_db: FastEdgy) -> None:
    finished: list[bool] = []

    async def late() -> None:
        await asyncio.sleep(0.05)
        finished.append(True)

    run_signal_side_effect(late, "late")
    await truncate_all_tables()

    assert finished == [True]
