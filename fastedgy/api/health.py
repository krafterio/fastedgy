# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from fastedgy.dependencies import get_service
from fastedgy.health import Health
from fastedgy.schemas.health import Health as HealthStatus


router = APIRouter(prefix="/health", tags=["health"])


@router.get("", tags=["health"])
async def health_check() -> HealthStatus:
    """Readiness endpoint: 200 only when this worker is fully started and
    not draining — the state itself lives in the Health service, this route
    only reflects it.
    """
    health = get_service(Health)

    if health.is_serving:
        return HealthStatus(status="ok")

    # 503 lets the orchestrator (and nginx's error_page → maintenance
    # mapping) treat a booting or draining replica as not routable.
    return JSONResponse(  # type: ignore[return-value]
        status_code=503,
        content={"status": "draining" if health.is_shutting_down else "starting"},
        headers={"Retry-After": "5"},
    )


__all__ = [
    "router",
]
