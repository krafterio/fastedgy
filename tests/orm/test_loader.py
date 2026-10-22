# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
from pathlib import Path

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.loader import load_data
from fastedgy.test.fixtures import stored_file_path
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product

_HEADER = "from fastedgy.orm.loader import id, ref, file\n"


def _write(directory: Path, name: str, content: str) -> None:
    (directory / name).write_text(_HEADER + content, encoding="utf-8")


async def test_creates_records_and_resolves_relations(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write(tmp_path, "category.py", 'data = [{"id": id("cat_books"), "name": "Books"}]')
    _write(tmp_path, "tag.py", 'data = [{"id": id("tag_new"), "name": "New"}]')
    _write(
        tmp_path,
        "product.py",
        'data = [{"id": id("p_laptop"), "name": "Laptop", "price": "999.00", '
        '"category": ref("cat_books"), "tags": [ref("tag_new")]}]',
    )

    report = await load_data(data_dir=str(tmp_path))

    assert report.created == 3
    assert await Product.query.count() == 1

    product = await Product.query.select_related("category").get(name="Laptop")

    assert product.category.name == "Books"
    assert [tag.name for tag in await product.tags.all()] == ["New"]


async def test_rerun_updates_without_duplicating(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write(tmp_path, "category.py", 'data = [{"id": id("cat"), "name": "Books"}]')

    assert (await load_data(data_dir=str(tmp_path))).created == 1

    _write(tmp_path, "category.py", 'data = [{"id": id("cat"), "name": "Literature"}]')
    report = await load_data(data_dir=str(tmp_path))

    assert report.created == 0
    assert report.updated == 1
    assert await Category.query.count() == 1
    assert (await Category.query.get()).name == "Literature"


async def test_rerun_without_changes_skips_update(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write(tmp_path, "category.py", 'data = [{"id": id("cat"), "name": "Books"}]')

    await load_data(data_dir=str(tmp_path))
    report = await load_data(data_dir=str(tmp_path))

    assert report.created == 0
    assert report.updated == 0


async def test_create_only_record_keeps_what_was_changed_since(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write(tmp_path, "category.py", 'data = [{"id": id("cat", update=False), "name": "Books"}]')

    assert (await load_data(data_dir=str(tmp_path))).created == 1

    category = await Category.query.get()
    category.name = "Edited in production"
    await category.save()

    _write(tmp_path, "category.py", 'data = [{"id": id("cat", update=False), "name": "Literature"}]')
    report = await load_data(data_dir=str(tmp_path))

    assert (report.created, report.updated) == (0, 0)
    assert (await Category.query.get()).name == "Edited in production"


async def test_create_only_record_deleted_since_stays_deleted(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write(tmp_path, "category.py", 'data = [{"id": id("cat", update=False), "name": "Books"}]')

    await load_data(data_dir=str(tmp_path))
    await (await Category.query.get()).delete()
    report = await load_data(data_dir=str(tmp_path))

    assert report.created == 0
    assert await Category.query.count() == 0


async def test_create_only_record_is_still_a_ref_target(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write(tmp_path, "category.py", 'data = [{"id": id("cat", update=False), "name": "Books"}]')

    await load_data(data_dir=str(tmp_path))

    _write(
        tmp_path,
        "product.py",
        'data = [{"id": id("p"), "name": "Novel", "price": "9.00", "category": ref("cat")}]',
    )
    await load_data(data_dir=str(tmp_path))

    product = await Product.query.select_related("category").get(name="Novel")

    assert product.category.name == "Books"


async def test_unknown_ref_raises(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write(
        tmp_path,
        "product.py",
        'data = [{"id": id("p"), "name": "Ghost", "price": "1.00", "category": ref("missing")}]',
    )

    with pytest.raises(ValueError):
        await load_data(data_dir=str(tmp_path))


async def test_file_uploads_and_stores_relative_path(setup_db: FastEdgy, tmp_path: Path) -> None:
    asset = tmp_path / "note.txt"
    asset.write_bytes(b"content")
    _write(
        tmp_path,
        "category.py",
        f'data = [{{"id": id("cat"), "name": "Books", "description": file({os.fspath(asset)!r})}}]',
    )

    await load_data(data_dir=str(tmp_path))

    category = await Category.query.get(name="Books")

    assert category.description.startswith("category/")
    assert os.path.exists(stored_file_path(category.description))
