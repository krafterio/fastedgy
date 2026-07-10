# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging

from fastedgy.app import FastEdgy
from fastedgy.orm import drain_signal_side_effects, run_signal_side_effect
from fastedgy.orm.exceptions import ObjectNotFound


async def _settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


async def test_side_effect_runs_after_spawn(setup_db: FastEdgy) -> None:
    ran: list[bool] = []

    async def op() -> None:
        ran.append(True)

    # Outside a transaction the deferred spawn runs immediately.
    run_signal_side_effect(op, "test side effect")
    await _settle()

    assert ran == [True]


async def test_deleted_entity_is_an_info_skip(setup_db: FastEdgy, caplog) -> None:
    async def vanished() -> None:
        raise ObjectNotFound("row does not exist anymore")

    with caplog.at_level(logging.INFO, logger="fastedgy.transaction"):
        run_signal_side_effect(vanished, "test skip")
        await _settle()

    assert any("skipping" in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_failure_is_logged_without_raising(setup_db: FastEdgy, caplog) -> None:
    async def broken() -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="fastedgy.transaction"):
        run_signal_side_effect(broken, "test failure")
        await _settle()

    assert any("test failure: boom" in r.getMessage() for r in caplog.records)


async def test_drain_waits_for_short_side_effects(setup_db: FastEdgy) -> None:
    done: list[bool] = []

    async def slow() -> None:
        await asyncio.sleep(0.1)
        done.append(True)

    run_signal_side_effect(slow, "test drain")
    await drain_signal_side_effects(timeout=5)

    assert done == [True]


async def test_drain_cancels_hung_side_effects(setup_db: FastEdgy, caplog) -> None:
    async def hung() -> None:
        await asyncio.sleep(3600)

    with caplog.at_level(logging.WARNING, logger="fastedgy.transaction"):
        run_signal_side_effect(hung, "test hung")
        await asyncio.sleep(0)
        await drain_signal_side_effects(timeout=0.05)

    assert any("Cancelled 1 signal side effect" in r.getMessage() for r in caplog.records)
