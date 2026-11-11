# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A file a record lets go (replaced, cleared, or deleted with the record) is removed by a queued task once the
transaction commits, with its optimized variants, unless a file field of some model still holds it."""

import os

import httpx

from fastedgy.dependencies import get_service
from fastedgy.storage import Storage
from fastedgy.storage.cleanup import schedule_file_cleanup
from fastedgy.storage.routing import is_global_storage_model
from fastedgy.test.factories import run_queued_tasks
from fastedgy.test.fixtures import STORAGE_ROOT, stored_file_path
from fastedgy.test.images import encoded_image
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product


def _png() -> bytes:
    return encoded_image((40, 20), "png", (255, 0, 0))


async def _uploaded(client: httpx.AsyncClient, product_id: int) -> str:
    response = await client.post(
        f"/api/storage/upload/product/{product_id}/image", files={"file": ("photo.png", _png(), "image/png")}
    )
    assert response.status_code == 200, response.text

    return response.json()["path"]


async def _product_with_image(client: httpx.AsyncClient) -> tuple[int, str]:
    product_id = (await Product.query.create(name="Laptop", price="10.00")).id
    path = await _uploaded(client, product_id)
    await get_service(Storage).get_optimized_or_original(path, w=10, global_storage=True)

    return product_id, path


def _kept(path: str) -> tuple[bool, bool]:
    return (
        os.path.exists(stored_file_path(path)),
        os.path.exists(os.path.join(STORAGE_ROOT, "cache_optimized_images", "global", path)),
    )


async def test_a_replaced_file_goes_with_its_variants_once_the_cleanup_task_ran(auth_http: httpx.AsyncClient) -> None:
    product_id, previous = await _product_with_image(auth_http)

    await _uploaded(auth_http, product_id)

    assert _kept(previous) == (True, True)
    assert await run_queued_tasks() >= 1
    assert _kept(previous) == (False, False)


async def test_a_path_written_over_a_file_removes_it(auth_http: httpx.AsyncClient) -> None:
    product_id, previous = await _product_with_image(auth_http)

    response = await auth_http.patch(f"/api/test_products/{product_id}", json={"image": "shared/cover.png"})
    await run_queued_tasks()

    assert response.status_code == 200, response.text
    assert _kept(previous) == (False, False)


async def test_a_file_another_model_holds_stays_until_it_lets_go(auth_http: httpx.AsyncClient) -> None:
    product_id, shared = await _product_with_image(auth_http)
    category = await Category.query.create(name="Books", image=shared)

    await _uploaded(auth_http, product_id)
    await run_queued_tasks()

    assert _kept(shared) == (True, True)

    await auth_http.patch(f"/api/test_categories/{category.id}", json={"image": None})
    await run_queued_tasks()

    assert _kept(shared) == (False, False)


async def test_a_deleted_record_takes_its_files_with_it(auth_http: httpx.AsyncClient) -> None:
    deleted, by_route = await _product_with_image(auth_http)
    queried, by_query = await _product_with_image(auth_http)

    response = await auth_http.delete(f"/api/test_products/{deleted}")
    await Product.query.filter(id=queried).delete()
    await run_queued_tasks()

    assert response.is_success, response.text
    assert (_kept(by_route), _kept(by_query)) == ((False, False), (False, False))


async def test_a_text_field_lets_go_only_the_files_of_the_directory_of_its_model(auth_http: httpx.AsyncClient) -> None:
    storage = get_service(Storage)
    global_storage = is_global_storage_model(Category)
    own = await storage.upload_from_bytes(b"own", "category", mime_type="text/plain", global_storage=global_storage)
    table = await storage.upload_from_bytes(
        b"table", "test_categories", mime_type="text/plain", global_storage=global_storage
    )

    schedule_file_cleanup(Category, "description", own, global_storage)
    schedule_file_cleanup(Category, "description", table, global_storage)
    await run_queued_tasks()

    assert not os.path.exists(stored_file_path(own))
    assert os.path.exists(stored_file_path(table))
