# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import ipaddress
import socket
from dataclasses import dataclass

import httpx
from anyio import to_thread

DEFAULT_MAX_REDIRECTS = 3
DEFAULT_TIMEOUT = 15.0


class UnsafeUrlError(Exception):
    pass


class ResponseTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class FetchedResponse:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes

    def __post_init__(self) -> None:
        # The content is held decoded: an encoding header left with it would be applied to it a second time
        headers = httpx.Headers(self.headers)
        headers.pop("content-encoding", None)
        object.__setattr__(self, "headers", headers)

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")

    @property
    def text(self) -> str:
        return httpx.Response(self.status_code, headers=self.headers, content=self.content).text


def _resolve(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


async def public_addresses(host: str) -> list[str]:
    try:
        resolved = await to_thread.run_sync(_resolve, host)
    except OSError, UnicodeError:
        return []

    addresses = list(dict.fromkeys(resolved))

    return addresses if addresses and all(ipaddress.ip_address(a).is_global for a in addresses) else []


async def ensure_public_url(url: str) -> list[str]:
    target = httpx.URL(url)

    if target.scheme not in ("http", "https") or not target.host:
        raise UnsafeUrlError(f"{url} is not an http or https url")

    addresses = await public_addresses(target.host)

    if not addresses:
        raise UnsafeUrlError(f"{target.host} does not lead to a public address")

    return addresses


class PublicTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        address = (await ensure_public_url(str(request.url)))[0]
        extensions = dict(request.extensions)

        if request.url.scheme == "https":
            extensions["sni_hostname"] = request.url.host

        # The client keeps the request it sent: its url, cookies and redirects stay on the host, not on the address
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=address),
            headers=request.headers,
            stream=request.stream,
            extensions=extensions,
        )

        return await self._transport.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self._transport.aclose()


def public_client(
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    transport: httpx.AsyncBaseTransport | None = None,
    **kwargs,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=PublicTransport(transport),
        follow_redirects=True,
        max_redirects=max_redirects,
        timeout=timeout,
        **kwargs,
    )


async def safe_get(
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedResponse:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
        for _ in range(max_redirects + 1):
            target = httpx.URL(url)
            address = (await ensure_public_url(url))[0]
            request_headers = {**(headers or {}), "Host": target.netloc.decode("ascii")}
            extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}

            async with client.stream(
                "GET", target.copy_with(host=address), headers=request_headers, extensions=extensions
            ) as response:
                if response.is_redirect and response.headers.get("location"):
                    url = str(target.join(response.headers["location"]))
                    continue

                chunks: list[bytes] = []
                received = 0

                async for chunk in response.aiter_bytes():
                    received += len(chunk)

                    if received > max_bytes:
                        raise ResponseTooLargeError(f"{url} answers more than {max_bytes} bytes")

                    chunks.append(chunk)

                return FetchedResponse(url, response.status_code, response.headers, b"".join(chunks))

    raise UnsafeUrlError(f"{url} redirects more than {max_redirects} times")


__all__ = [
    "FetchedResponse",
    "PublicTransport",
    "ResponseTooLargeError",
    "UnsafeUrlError",
    "ensure_public_url",
    "public_addresses",
    "public_client",
    "safe_get",
]
