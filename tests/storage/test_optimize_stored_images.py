# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.storage import Storage
from fastedgy.storage.images import optimize_stored_images
from fastedgy.test.fixtures import STORAGE_ROOT, stored_file_path
from fastedgy.test.images import described_image, encoded_image
from fastedgy.test.models.product import Product


async def _stored_png(size: tuple[int, int] = (3000, 1500)) -> str:
    buffer = encoded_image(size, "png", (255, 0, 0))

    return await get_service(Storage).upload_from_bytes(
        buffer, "test_products", mime_type="image/png", global_storage=True
    )


async def _product(image: str) -> int:
    return (await Product.query.create(name="Laptop", price="10.00", image=image)).id


async def _image(product_id: int) -> str | None:
    return (await Product.query.get(id=product_id)).image


async def test_a_dry_run_counts_the_images_and_changes_nothing(setup_db: FastEdgy) -> None:
    path = await _stored_png()
    product_id = await _product(path)

    report = await optimize_stored_images(dry_run=True)

    assert report.files == {"product.image": 1}
    assert report.optimized == 0
    assert await _image(product_id) == path
    assert os.path.isfile(stored_file_path(path))


async def test_a_stored_image_is_rewritten_for_every_record_holding_it(setup_db: FastEdgy) -> None:
    path = await _stored_png()
    first, second = await _product(path), await _product(path)
    await get_service(Storage).get_optimized_or_original(path, w=10, global_storage=True)
    cache = os.path.join(STORAGE_ROOT, "cache_optimized_images", "global", path)
    assert os.path.isdir(cache)

    updated_at = (await Product.query.get(id=first)).updated_at

    report = await optimize_stored_images()
    rewritten = await _image(first)

    assert report.optimized == 1
    assert (await Product.query.get(id=first)).updated_at != updated_at
    assert rewritten is not None and rewritten.startswith("test_products/") and rewritten.endswith(".webp")
    assert await _image(second) == rewritten
    assert described_image(stored_file_path(rewritten))[1] == (2560, 1280)
    assert not os.path.exists(stored_file_path(path))
    assert not os.path.exists(cache)


async def test_an_optimized_image_is_left_alone(setup_db: FastEdgy) -> None:
    product_id = await _product(await _stored_png())
    await optimize_stored_images()
    rewritten = await _image(product_id)

    report = await optimize_stored_images()

    assert (report.optimized, report.unchanged) == (0, 1)
    assert await _image(product_id) == rewritten


async def test_a_model_filter_leaves_the_other_models_alone(setup_db: FastEdgy) -> None:
    path = await _stored_png()
    product_id = await _product(path)

    report = await optimize_stored_images(model="category")

    assert report.files == {}
    assert await _image(product_id) == path


async def test_a_missing_file_is_counted_and_kept(setup_db: FastEdgy) -> None:
    product_id = await _product("test_products/gone.png")

    report = await optimize_stored_images()

    assert report.missing == 1
    assert await _image(product_id) == "test_products/gone.png"
