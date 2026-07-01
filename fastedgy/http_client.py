# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

from typing import Any

import httpx


DEFAULT_RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def create_http_client(
    timeout: float = 30.0,
    retries: int = 3,
    follow_redirects: bool = True,
    **kwargs: Any,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        transport=httpx.AsyncHTTPTransport(retries=retries),
        **kwargs,
    )


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    retry_status_codes: frozenset[int] = DEFAULT_RETRY_STATUS_CODES,
    **kwargs: Any,
) -> httpx.Response:
    last_response: httpx.Response | None = None
    last_exc: httpx.RequestError | None = None

    for attempt in range(max_retries + 1):
        try:
            last_response = await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            last_exc = exc
            last_response = None
        else:
            if last_response.status_code not in retry_status_codes:
                return last_response

        if attempt < max_retries:
            await asyncio.sleep(backoff_factor * 2**attempt)

    if last_response is not None:
        return last_response

    assert last_exc is not None
    raise last_exc


__all__ = [
    "DEFAULT_RETRY_STATUS_CODES",
    "create_http_client",
    "request_with_retry",
]
