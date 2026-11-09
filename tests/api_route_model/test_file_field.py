# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A file field takes a data URL through the API: the file is stored the way the upload route stores
one, and its path is what the record keeps."""

import base64
import os

import httpx

from fastedgy.test.factories import run_queued_tasks
from fastedgy.test.fixtures import stored_file_path
from fastedgy.test.images import described_image, encoded_image

from .helpers import make_product


def _data_url(size: tuple[int, int] = (3000, 1500), content_type: str = "image/png") -> str:
    buffer = encoded_image(size, "png", (255, 0, 0))

    return f"data:{content_type};base64,{base64.b64encode(buffer).decode()}"


async def _image(client: httpx.AsyncClient, product_id: int) -> str | None:
    response = await client.get(f"/api/test_products/{product_id}", headers={"X-Fields": "image"})

    return response.json()["image"]


async def test_a_data_url_written_at_creation_is_stored_optimized(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, image=_data_url())
    path = await _image(auth_http, product["id"])

    assert path is not None and path.startswith("test_products/") and path.endswith(".webp")
    assert described_image(stored_file_path(path))[1] == (2560, 1280)


async def test_a_data_url_replaces_the_file_of_the_record(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, image=_data_url())
    previous = await _image(auth_http, product["id"])

    response = await auth_http.patch(f"/api/test_products/{product['id']}", json={"image": _data_url((40, 20))})
    await run_queued_tasks()
    path = await _image(auth_http, product["id"])

    assert response.status_code == 200, response.text
    assert path != previous and path is not None
    assert described_image(stored_file_path(path))[1] == (40, 20)
    assert previous is not None and not os.path.isfile(stored_file_path(previous))


async def test_a_cleared_field_removes_its_file(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, image=_data_url((40, 20)))
    previous = await _image(auth_http, product["id"])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"image": None})
    await run_queued_tasks()

    assert await _image(auth_http, product["id"]) is None
    assert previous is not None and not os.path.isfile(stored_file_path(previous))


async def test_a_storage_path_is_written_as_is(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http)

    response = await auth_http.patch(f"/api/test_products/{product['id']}", json={"image": "shared/cover.png"})

    assert response.status_code == 200, response.text
    assert await _image(auth_http, product["id"]) == "shared/cover.png"


async def test_a_data_url_of_a_refused_type_stores_nothing(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http)
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode()
    stored_before = _stored_product_files()

    response = await auth_http.patch(f"/api/test_products/{product['id']}", json={"image": svg})

    assert response.status_code == 422
    assert await _image(auth_http, product["id"]) is None
    assert _stored_product_files() == stored_before


async def test_a_synced_data_url_is_stored(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http)
    base = (await auth_http.get(f"/api/test_products/{product['id']}")).json()
    operation = {
        "op": "update",
        "id": product["id"],
        "payload": {"image": _data_url((40, 20))},
        "base": base,
        "created_at": "2100-01-01T00:00:00Z",
    }

    response = await auth_http.post("/api/test_products/sync", json={"operations": [operation]})
    path = await _image(auth_http, product["id"])

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "applied"
    assert path is not None and path.endswith(".webp") and os.path.isfile(stored_file_path(path))


def _stored_product_files() -> set[str]:
    directory = stored_file_path("test_products")

    return set(os.listdir(directory)) if os.path.isdir(directory) else set()
