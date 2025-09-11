# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import FastAPI
from contextlib import AsyncExitStack
from typing import Callable, TypeVar, Any
from fastapi.dependencies.utils import get_dependant, solve_dependencies as base_solve_dependencies
from starlette.requests import Request


T = TypeVar('T')


async def depends(app: FastAPI | None, call: Callable[..., T]) -> T:
    values = await solve_dependencies(app, None, call)

    return call(**values)


async def solve_dependencies(app: FastAPI | None, request: Request | None, call: Callable[..., T], skip_error: bool = False) -> dict[str, Any]:
    if not request:
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        })
    dependant = get_dependant(path="", call=call)
    exit_stack = AsyncExitStack()
    solved = await base_solve_dependencies(
        request=request,
        dependant=dependant,
        dependency_overrides_provider=app,
        async_exit_stack=exit_stack,
        embed_body_fields=False,
    )
    await exit_stack.aclose()

    if solved.errors and not skip_error:
        raise RuntimeError(f"Dependency Injection Error: {solved.errors}")

    return solved.values
