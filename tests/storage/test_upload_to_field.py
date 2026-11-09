# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""What the server stores for a model field goes through Storage.upload_to_field: the file is stored as the upload
route stores it, optimized when the field is an ImageField."""

import os
from pathlib import Path

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.storage import Storage
from fastedgy.test.factories import run_queued_tasks
from fastedgy.test.fixtures import stored_file_path
from fastedgy.test.images import described_image, encoded_image
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product


def _png(size: tuple[int, int] = (3000, 1500)) -> bytes:
    return encoded_image(size, "png", (255, 0, 0))


async def test_bytes_for_an_image_field_are_stored_optimized(setup_db: FastEdgy) -> None:
    path = await get_service(Storage).upload_to_field(Product, "image", _png(), mime_type="image/png")
    stored = described_image(stored_file_path(path))

    assert path.startswith("test_products/") and path.endswith(".webp")
    assert stored == ("WEBP", (2560, 1280))


async def test_a_file_for_a_field_of_a_record_replaces_the_one_it_held(setup_db: FastEdgy) -> None:
    storage = get_service(Storage)
    product = await Product.query.create(name="Laptop", price="10.00")
    previous = await storage.upload_to_field(Product, "image", _png((40, 20)), mime_type="image/png", record=product)
    await product.save()

    path = await storage.upload_to_field(Product, "image", _png((40, 20)), mime_type="image/png", record=product)
    await product.save()
    await run_queued_tasks()

    assert (await Product.query.get(id=product.id)).image == path
    assert os.path.isfile(stored_file_path(path))
    assert not os.path.isfile(stored_file_path(previous))


async def test_a_file_for_a_field_that_is_no_image_is_stored_as_is(setup_db: FastEdgy) -> None:
    path = await get_service(Storage).upload_to_field(Category, "description", b"plain text", mime_type="text/plain")

    assert path.startswith("test_categories/") and path.endswith(".txt")
    assert Path(stored_file_path(path)).read_bytes() == b"plain text"
