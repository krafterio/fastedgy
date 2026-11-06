# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
import pytest

from fastedgy import safe_fetch
from fastedgy.safe_fetch import ResponseTooLargeError, UnsafeUrlError, safe_get

ADDRESSES = {"example.io": "93.184.216.34", "internal.example.io": "10.0.0.5", "rebind.example.io": "127.0.0.1"}


@pytest.fixture(autouse=True)
def resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safe_fetch, "_resolve", lambda host: [ADDRESSES.get(host, host)])


def _transport(routes: dict[str, httpx.Response], seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)

        return routes.get(f"{request.headers['host']}{request.url.path}", httpx.Response(404))

    return httpx.MockTransport(handle)


async def test_a_public_url_is_read_from_the_address_it_resolved_to() -> None:
    seen: list[httpx.Request] = []
    transport = _transport({"example.io/page": httpx.Response(200, content=b"hello")}, seen)

    response = await safe_get("https://example.io/page", max_bytes=100, transport=transport)

    assert response.content == b"hello"
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "example.io"
    assert seen[0].extensions["sni_hostname"] == "example.io"


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/", "http://169.254.169.254/latest", "http://internal.example.io/", "ftp://example.io/"]
)
async def test_a_url_leading_outside_the_public_network_is_refused(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await safe_get(url, max_bytes=100, transport=_transport({}))


async def test_a_redirect_into_the_internal_network_is_refused() -> None:
    transport = _transport(
        {"example.io/go": httpx.Response(302, headers={"location": "http://rebind.example.io/admin"})}
    )

    with pytest.raises(UnsafeUrlError):
        await safe_get("https://example.io/go", max_bytes=100, transport=transport)


async def test_a_body_past_the_limit_is_dropped() -> None:
    transport = _transport({"example.io/big": httpx.Response(200, content=b"x" * 101)})

    with pytest.raises(ResponseTooLargeError):
        await safe_get("https://example.io/big", max_bytes=100, transport=transport)


async def test_a_redirect_loop_ends() -> None:
    transport = _transport({"example.io/loop": httpx.Response(302, headers={"location": "/loop"})})

    with pytest.raises(UnsafeUrlError):
        await safe_get("https://example.io/loop", max_bytes=100, transport=transport)


def test_a_refusal_is_not_a_network_error() -> None:
    assert not issubclass(UnsafeUrlError, httpx.RequestError)
    assert not issubclass(ResponseTooLargeError, httpx.RequestError)


async def test_the_storage_downloads_no_url_of_the_internal_network(setup_db: object) -> None:
    from fastedgy.dependencies import get_service
    from fastedgy.storage import Storage

    with pytest.raises(ValueError):
        await get_service(Storage).download_and_upload("http://169.254.169.254/latest/meta-data", "imports")
