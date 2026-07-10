# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
import pytest

from sqlalchemy.exc import DBAPIError

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.health import Health


def _serialization_loss() -> DBAPIError:
    return DBAPIError(
        "DELETE FROM users WHERE users.id = $1::INTEGER",
        {},
        Exception("could not serialize access due to read/write dependencies among transactions"),
    )


@pytest.fixture
def health(setup_db: FastEdgy):
    service = get_service(Health)
    ready, shutting_down = service._ready, service._shutting_down
    yield service
    service._ready, service._shutting_down = ready, shutting_down


async def test_serialization_loss_is_maintenance_during_the_deploy_window(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient, health: Health
) -> None:
    async def lost_the_race() -> None:
        raise _serialization_loss()

    setup_db.add_api_route("/api/test-serialization-window", lost_the_race, methods=["DELETE"])
    # A draining worker is in the window by definition.
    health.mark_shutting_down()

    response = await setup_http.delete("/api/test-serialization-window")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


async def test_serialization_loss_stays_an_error_in_steady_state(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient, health: Health
) -> None:
    async def lost_the_race() -> None:
        raise _serialization_loss()

    setup_db.add_api_route("/api/test-serialization-steady", lost_the_race, methods=["DELETE"])
    health._shutting_down = False

    with pytest.raises(DBAPIError):
        await setup_http.delete("/api/test-serialization-steady")


async def test_normal_traffic_is_untouched_during_the_window(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient, health: Health
) -> None:
    async def fine() -> dict:
        return {"ok": True}

    setup_db.add_api_route("/api/test-fine-during-deploy", fine, methods=["GET"])
    health.mark_shutting_down()

    response = await setup_http.get("/api/test-fine-during-deploy")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
