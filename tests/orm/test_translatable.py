# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import StatementError

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.i18n import _ts
from fastedgy.metadata_model.generator import generate_metadata_field
from fastedgy.orm import Registry
from fastedgy.orm.fields import read_translations
from fastedgy.orm.fields.field_fulltext import build_tsvector_expression
from fastedgy.orm.filter import R
from fastedgy.test.models.category import Category
from fastedgy.test.models.course import Course


@pytest.fixture(autouse=True)
def locales(override_settings: Callable[..., None]) -> None:
    override_settings(available_locales=["en", "fr", "de"], fallback_locale="en")


async def _create(title: str | dict[str, str | None] = "Chair", **values: Any) -> Course:
    course = Course(code=values.pop("code", "C1"), title=title, **values)
    await course.save()

    return course


async def _get(course: Course) -> Course:
    return await Course.query.get(id=course.id)


async def _row(course: Course, column: str = "title") -> Any:
    database = get_service(Registry).database

    return await database.fetch_val(f"SELECT {column} FROM test_courses WHERE id = :id", {"id": course.id})


# --- Reads and writes --------------------------------------------------------


async def test_a_creation_stores_the_text_under_its_locale(setup_db: FastEdgy) -> None:
    course = await _create("Chair")

    assert await read_translations(course, "title") == {"en": "Chair"}
    assert course.title == "Chair"


async def test_a_creation_in_another_locale_fills_the_fallback_too(setup_db: FastEdgy) -> None:
    with context.locale("fr"):
        course = await _create("Chaise")

    assert await read_translations(course, "title") == {"en": "Chaise", "fr": "Chaise"}


async def test_a_read_answers_the_locale_then_the_fallback(setup_db: FastEdgy) -> None:
    course = await _create("Chair")

    with context.locale("fr"):
        assert (await _get(course)).title == "Chair"

        course.title = "Chaise"
        await course.save()

        assert (await _get(course)).title == "Chaise"

    assert (await _get(course)).title == "Chair"

    with context.locale("de"):
        assert (await _get(course)).title == "Chair"


async def test_writing_a_locale_leaves_the_others_alone(setup_db: FastEdgy) -> None:
    course = await _create("Chair")

    with context.locale("fr"):
        await course.update(title="Chaise")

    with context.locale("de"):
        await course.update(title="Stuhl")

    await course.update(title="Armchair")

    assert await read_translations(course, "title") == {"en": "Armchair", "fr": "Chaise", "de": "Stuhl"}


async def test_saving_what_a_locale_reads_through_the_fallback_writes_no_translation(setup_db: FastEdgy) -> None:
    course = await _create("Chair")

    with context.locale("fr"):
        loaded = await _get(course)
        loaded.code = "C2"
        await loaded.save()

    assert await read_translations(course, "title") == {"en": "Chair"}
    assert (await _get(course)).code == "C2"


async def test_none_removes_the_locale_and_an_empty_document_is_null(setup_db: FastEdgy) -> None:
    course = await _create("Chair", summary="Wooden")

    with context.locale("fr"):
        await course.update(summary="En bois")
        await course.update(summary=None)

    assert await read_translations(course, "summary") == {"en": "Wooden"}

    await course.update(summary=None)

    assert await _row(course, "summary") is None
    assert (await _get(course)).summary is None


async def test_a_message_to_translate_writes_every_locale_it_is_translated_in(
    setup_db: FastEdgy, override_settings: Callable[..., None]
) -> None:
    override_settings(available_locales=["en", "fr", "pt"])
    course = await _create(_ts("User"))

    assert await read_translations(course, "title") == {"en": "User", "fr": "Utilisateur"}
    assert course.title == "User"

    with context.locale("fr"):
        await course.update(title="Membre")
        await course.update(title=_ts("User"))

        assert course.title == "Utilisateur"

    assert await read_translations(course, "title") == {"en": "User", "fr": "Utilisateur"}


async def test_translations_keyed_by_locale_set_each_of_them(setup_db: FastEdgy) -> None:
    course = await _create({"fr": "Chaise", "de": "Stuhl"})

    assert await read_translations(course, "title") == {"en": "Chaise", "fr": "Chaise", "de": "Stuhl"}
    assert course.title == "Chaise"

    await course.update(title={"en": "Chair", "de": None})

    assert await read_translations(course, "title") == {"en": "Chair", "fr": "Chaise"}

    with context.locale("fr"):
        assert (await _get(course)).title == "Chaise"


async def test_a_write_refuses_a_locale_outside_the_available_ones(setup_db: FastEdgy) -> None:
    with pytest.raises(ValidationError, match="Unavailable locale: it"):
        Course(code="C1", title={"it": "Sedia"})

    course = await _create("Chair")

    with pytest.raises(StatementError, match="Unavailable locale: it"):
        await course.update(title={"it": "Sedia"})

    with context.locale("it"), pytest.raises(StatementError, match="Unavailable locale: it"):
        await course.update(title="Sedia")

    assert await read_translations(course, "title") == {"en": "Chair"}


async def test_each_translation_is_validated_as_the_text_it_is(setup_db: FastEdgy) -> None:
    with pytest.raises(ValidationError, match="at most 40 characters"):
        Course(code="C1", title={"fr": "x" * 41})

    with pytest.raises(ValidationError, match="fallback locale en is required"):
        Course(code="C1", title={"en": None, "fr": "Chaise"})

    assert Course(code="C1", title={"en": "a", "fr": "b", "de": "c"}).title == {"en": "a", "fr": "b", "de": "c"}
    assert Course(code="C1", title="Chair", summary={"en": None}).summary == {"en": None}


def test_a_translatable_field_is_neither_unique_nor_a_primary_key() -> None:
    from edgy.exceptions import FieldDefinitionError

    from fastedgy.orm import fields

    with pytest.raises(FieldDefinitionError, match="neither unique nor a primary key"):
        fields.CharField(max_length=40, translatable=True, unique=True)


async def test_every_write_path_merges_into_the_document(setup_db: FastEdgy) -> None:
    first = await _create("Chair", code="A")
    second = await _create("Table", code="B")

    with context.locale("fr"):
        await Course.query.filter(code="A").update(title="Chaise")

        rows = await Course.query.order_by("code").all()
        rows[1].title = "Table basse"
        await Course.query.bulk_update(rows, fields=["title"])

        await Course.query.bulk_create([{"code": "C", "title": "Lampe"}])

    assert await read_translations(first, "title") == {"en": "Chair", "fr": "Chaise"}
    assert await read_translations(second, "title") == {"en": "Table", "fr": "Table basse"}
    assert await read_translations(await Course.query.get(code="C"), "title") == {"en": "Lampe", "fr": "Lampe"}


async def test_a_field_without_the_option_keeps_its_text_column(setup_db: FastEdgy) -> None:
    course = await _create("Chair", code="PLAIN")

    assert await _row(course, "code") == "PLAIN"
    assert str(Course.table.columns["code"].type) == "VARCHAR(20)"


# --- Queries -----------------------------------------------------------------


async def test_a_filter_compares_the_text_the_locale_reads(setup_db: FastEdgy) -> None:
    chair = await _create("Chair", code="A")
    await _create("Table", code="B")

    with context.locale("fr"):
        await chair.update(title="Chaise")

        assert [c.code for c in await Course.query.filter(title="Chaise").all()] == ["A"]
        assert [c.code for c in await Course.query.filter(title__icontains="tab").all()] == ["B"]
        assert [c.code for c in await Course.query.filter(R("title", "in", ["Chaise", "Table"])).order_by("code")] == [
            "A",
            "B",
        ]
        assert await Course.query.filter(R("summary", "is empty")).count() == 2

    assert await Course.query.filter(title="Chaise").count() == 0
    assert [c.code for c in await Course.query.filter(R("title", "starts with", "Ch")).all()] == ["A"]


async def test_an_order_follows_the_text_the_locale_reads(setup_db: FastEdgy) -> None:
    await _create("Apple", code="A")
    banana = await _create("Banana", code="B")

    with context.locale("fr"):
        await banana.update(title="Abricot")

        assert [c.code for c in await Course.query.order_by("title").all()] == ["B", "A"]
        assert [c.code for c in await Course.query.order_by("-title").all()] == ["A", "B"]

    assert [c.code for c in await Course.query.order_by("title").all()] == ["A", "B"]


async def test_a_relation_reads_filters_and_orders_in_the_locale(setup_db: FastEdgy) -> None:
    furniture = await Category.query.create(name="Furniture")
    lighting = await Category.query.create(name="Lighting")
    await _create("Chair", code="A", category=furniture)
    lamp = await _create("Lamp", code="B", category=lighting)

    with context.locale("fr"):
        await lamp.update(title="Abat-jour")

        assert [c.name for c in await Category.query.filter(R("courses.title", "=", "Abat-jour")).all()] == ["Lighting"]
        assert [c.name for c in await Category.query.order_by("courses__title").all()] == ["Lighting", "Furniture"]

        values = await Course.query.order_by("code").values(["code", "title"])

        assert values == [{"code": "A", "title": "Chair"}, {"code": "B", "title": "Abat-jour"}]

        assert [c.title for c in await lighting.courses.all()] == ["Abat-jour"]

        course = await Course.query.select_related("category").get(code="B")

        assert (course.title, course.category.name) == ("Abat-jour", "Lighting")


# --- What builds on the field ------------------------------------------------


async def test_the_vector_of_a_locale_reads_its_text_then_the_fallback(setup_db: FastEdgy) -> None:
    with context.locale("fr"):
        course = await _create("Chaise pliante")

    expression = build_tsvector_expression(Course, "fr")

    assert expression is not None
    assert "coalesce(\"title\" ->> 'fr', \"title\" ->> 'en')" in expression
    assert "chais" in str(await _row(course, f"({expression})::text"))
    assert "chais" in str(await _row(course, "search_value_en::text"))


async def test_a_duplicate_carries_every_locale(setup_db: FastEdgy) -> None:
    course = await _create("Chair", summary="Wooden")

    with context.locale("fr"):
        await course.update(title="Chaise", summary="En bois")

    copy = await course.duplicate({"code": "C2", "summary": "Copied"})

    assert await read_translations(copy, "title") == {"en": "Chair", "fr": "Chaise"}
    assert await read_translations(copy, "summary") == {"en": "Copied"}


async def test_the_metadata_says_which_fields_are_translatable(setup_db: FastEdgy) -> None:
    assert generate_metadata_field(Course, Course.meta.fields["title"]).translatable is True
    assert generate_metadata_field(Course, Course.meta.fields["code"]).translatable is False


async def test_the_data_loader_rewrites_a_message_whose_translations_changed(
    setup_db: FastEdgy, tmp_path: Any, override_settings: Callable[..., None]
) -> None:
    from fastedgy.orm.loader import load_data

    (tmp_path / "course.py").write_text(
        "from fastedgy.i18n import _ts\nfrom fastedgy.orm.loader import id\n\n"
        'data = [{"id": id("course_user"), "code": "U", "title": _ts("User")}]\n',
        encoding="utf-8",
    )

    assert (await load_data(str(tmp_path))).created == 1
    assert (await load_data(str(tmp_path))).updated == 0

    override_settings(available_locales=["en"])
    report = await load_data(str(tmp_path))

    assert report.updated == 1
    assert await read_translations(await Course.query.get(code="U"), "title") == {"en": "User"}


async def test_the_data_loader_writes_translations_keyed_by_locale(setup_db: FastEdgy, tmp_path: Any) -> None:
    from fastedgy.orm.loader import load_data

    (tmp_path / "course.py").write_text(
        "from fastedgy.orm.loader import id\n\n"
        'data = [{"id": id("course_chair"), "code": "C", "title": {"en": "Chair", "fr": "Chaise"}}]\n',
        encoding="utf-8",
    )

    assert (await load_data(str(tmp_path))).created == 1
    assert (await load_data(str(tmp_path))).updated == 0
    assert await read_translations(await Course.query.get(code="C"), "title") == {"en": "Chair", "fr": "Chaise"}
