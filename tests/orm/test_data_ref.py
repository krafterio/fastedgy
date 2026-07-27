# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pathlib import Path

from typing import cast

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.models.data_record import DataRecord
from fastedgy.orm.data_ref import DataRefs
from fastedgy.orm.loader import load_data
from fastedgy.test.models.category import Category

_HEADER = "from fastedgy.orm.loader import id, ref, file\n"


def _write_category(directory: Path, key: str, name: str) -> None:
    content = f'data = [{{"id": id("{key}"), "name": "{name}"}}]'
    (directory / "category.py").write_text(_HEADER + content, encoding="utf-8")


async def test_resolves_a_loaded_key(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    category = await Category.query.get(name="Books")

    assert await DataRefs().id("cat_books") == category.id


async def test_unknown_key_resolves_to_nothing(setup_db: FastEdgy, tmp_path: Path) -> None:
    assert await DataRefs().id("cat_nothing") is None


async def test_the_service_is_registered_by_the_app(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    refs = cast(DataRefs, get_service(DataRefs))

    assert await refs.id("cat_books") == (await Category.query.get(name="Books")).id


async def test_a_resolution_is_cached(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    refs = DataRefs()
    resolved = await refs.id("cat_books")

    await DataRecord.query.filter(key="cat_books").delete()

    assert await refs.id("cat_books") == resolved


async def test_a_miss_is_not_cached(setup_db: FastEdgy, tmp_path: Path) -> None:
    refs = DataRefs()

    assert await refs.id("cat_books") is None

    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    assert await refs.id("cat_books") == (await Category.query.get(name="Books")).id


async def test_reset_forgets_what_was_resolved(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    refs = DataRefs()

    await refs.id("cat_books")
    await DataRecord.query.filter(key="cat_books").delete()
    refs.reset()

    assert await refs.id("cat_books") is None


async def test_reads_the_record_itself(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    category = await DataRefs().record("cat_books", Category)

    assert category is not None
    assert category.name == "Books"


async def test_a_key_naming_a_deleted_record_reads_as_nothing(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))
    await Category.query.filter(name="Books").delete()

    assert await DataRefs().record("cat_books", Category) is None


async def test_no_declared_key_means_no_system_user(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    assert await DataRefs().system_user_id() is None


async def test_the_declared_key_names_the_system_user(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_system", "System")
    await load_data(data_dir=str(tmp_path))

    refs = DataRefs(system_user_key="cat_system")

    assert await refs.system_user_id() == (await Category.query.get(name="System")).id


async def test_a_declared_key_that_names_nothing_stays_none(setup_db: FastEdgy, tmp_path: Path) -> None:
    refs = DataRefs(system_user_key="user_system")

    assert await refs.system_user_id() is None


async def test_loading_data_forgets_what_the_loader_resolved(setup_db: FastEdgy, tmp_path: Path) -> None:
    _write_category(tmp_path, "cat_books", "Books")
    await load_data(data_dir=str(tmp_path))

    refs = cast(DataRefs, get_service(DataRefs))
    resolved = await refs.id("cat_books")

    assert resolved is not None

    await DataRecord.query.filter(key="cat_books").delete()
    await Category.query.filter(name="Books").delete()
    await load_data(data_dir=str(tmp_path))

    assert await refs.id("cat_books") != resolved
