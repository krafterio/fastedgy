# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import zlib

import pytest

from sqlalchemy import text

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.health import Health
from fastedgy.orm import Database


@pytest.fixture
def health(setup_db: FastEdgy):
    service = get_service(Health)
    ready, shutting_down = service._ready, service._shutting_down
    yield service
    service._ready, service._shutting_down = ready, shutting_down


async def test_readiness_state_machine(health: Health) -> None:
    health._ready = False
    health._shutting_down = False
    assert health.is_serving is False

    health.mark_ready()
    assert health.is_ready is True
    assert health.is_serving is True

    health.mark_shutting_down()
    assert health.is_shutting_down is True
    assert health.is_serving is False


async def test_deploy_lock_key_derives_from_the_configured_name(health: Health, monkeypatch) -> None:
    monkeypatch.setattr(health._settings, "deploy_lock_name", "MELI")
    assert health.deploy_lock_key == zlib.crc32(b"MELI") & 0x7FFFFFFF

    monkeypatch.setattr(health._settings, "deploy_lock_name", "")
    assert health.deploy_lock_key is None


async def test_no_lock_name_means_no_orchestrator_window(health: Health, monkeypatch) -> None:
    monkeypatch.setattr(health._settings, "deploy_lock_name", "")
    health._shutting_down = False

    assert await health.in_deploy_window() is False


async def test_draining_worker_is_inside_the_window(health: Health) -> None:
    health.mark_shutting_down()

    assert await health.in_deploy_window() is True


async def test_advisory_lock_opens_and_closes_the_window(health: Health, monkeypatch) -> None:
    monkeypatch.setattr(health._settings, "deploy_lock_name", "test-deploy")
    health._shutting_down = False
    key = health.deploy_lock_key
    assert key is not None

    db = get_service(Database)

    assert await health.in_deploy_window() is False

    async with db.connection() as conn:
        await conn.execute(text(f"SELECT pg_advisory_lock({key})"))
        try:
            assert await health.in_deploy_window() is True
        finally:
            await conn.execute(text(f"SELECT pg_advisory_unlock({key})"))

    assert await health.in_deploy_window() is False
