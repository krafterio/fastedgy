# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import APIRouter
from fastedgy.schemas.health import HealthResult


router = APIRouter(prefix="/health", tags=["health"])


@router.get("", tags=["health"])
async def health_check() -> HealthResult:
    """
    Health check endpoint to verify the API is running.
    """
    return HealthResult(status="ok")


__all__ = [
    "router",
]
