# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
from fastapi import APIRouter
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from fastedgy.app import FastEdgy

ORIGIN = "http://localhost:5199"


def _failing_stack() -> ASGIApp:
    """The middleware stack of an app whose one route fails, its CORS added the way a project adds it."""
    router = APIRouter()

    @router.get("/fails")
    async def fails() -> None:
        raise RuntimeError("fails")

    app = object.__new__(FastEdgy)
    app.debug = False
    app.exception_handlers = {}
    app.user_middleware = [Middleware(CORSMiddleware, allow_origins=[ORIGIN])]
    app.router = router

    return app.build_middleware_stack()


async def test_an_unhandled_error_answers_with_the_cors_headers() -> None:
    transport = httpx.ASGITransport(app=_failing_stack(), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/fails", headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == ORIGIN
