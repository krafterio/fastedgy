# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import APIRouter
from fastedgy.schemas.health import Health


router = APIRouter(prefix="/health", tags=["health"])


@router.get("", tags=["health"])
async def health_check() -> Health:
    """
    Health check endpoint to verify the API is running.
    """
    return Health(status="ok")


__all__ = [
    "router",
]
