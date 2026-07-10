# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
import pytest

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.health import Health


@pytest.fixture
def health(setup_db: FastEdgy):
    service = get_service(Health)
    ready, shutting_down = service._ready, service._shutting_down
    yield service
    service._ready, service._shutting_down = ready, shutting_down


async def test_health_route_reflects_the_service_state(setup_http: httpx.AsyncClient, health: Health) -> None:
    health._ready = False
    health._shutting_down = False
    starting = await setup_http.get("/api/health")
    assert starting.status_code == 503
    assert starting.json() == {"status": "starting"}
    assert starting.headers["Retry-After"] == "5"

    health.mark_ready()
    serving = await setup_http.get("/api/health")
    assert serving.status_code == 200
    assert serving.json() == {"status": "ok"}

    health.mark_shutting_down()
    draining = await setup_http.get("/api/health")
    assert draining.status_code == 503
    assert draining.json() == {"status": "draining"}
