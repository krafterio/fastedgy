# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
import pytest

from fastedgy.http_client import (
    DEFAULT_RETRY_STATUS_CODES,
    create_http_client,
    request_with_retry,
)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_create_http_client_defaults() -> None:
    client = create_http_client()

    assert isinstance(client, httpx.AsyncClient)
    assert client.follow_redirects is True


def test_default_retry_status_codes() -> None:
    assert DEFAULT_RETRY_STATUS_CODES == frozenset({429, 500, 502, 503, 504})


async def test_request_with_retry_returns_first_success() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(200)
        return httpx.Response(200, text="ok")

    async with _client(handler) as client:
        response = await request_with_retry(client, "GET", "https://example.test/x", backoff_factor=0)

    assert response.status_code == 200
    assert len(calls) == 1


async def test_request_with_retry_retries_on_retryable_status() -> None:
    statuses = [503, 503, 200]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses[len(calls)]
        calls.append(status)
        return httpx.Response(status)

    async with _client(handler) as client:
        response = await request_with_retry(client, "GET", "https://example.test/x", backoff_factor=0)

    assert response.status_code == 200
    assert calls == [503, 503, 200]


async def test_request_with_retry_retries_on_request_error() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200)

    async with _client(handler) as client:
        response = await request_with_retry(client, "GET", "https://example.test/x", backoff_factor=0)

    assert response.status_code == 200
    assert len(calls) == 2


async def test_request_with_retry_exhausts_and_returns_last_response() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    async with _client(handler) as client:
        response = await request_with_retry(client, "GET", "https://example.test/x", max_retries=2, backoff_factor=0)

    assert response.status_code == 503
    assert len(calls) == 3


async def test_request_with_retry_raises_last_request_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async with _client(handler) as client:
        with pytest.raises(httpx.ConnectError):
            await request_with_retry(client, "GET", "https://example.test/x", max_retries=1, backoff_factor=0)
