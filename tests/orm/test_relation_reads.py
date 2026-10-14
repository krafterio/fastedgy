# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A read hands over of the records its relations reach only what the request
may read: a to-one relation it may not read keeps its key alone."""

import csv
import io
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.dataflow.exporter import export_data
from fastedgy.orm.field_selector import (
    apply_field_map_optimizations,
    filter_selected_fields,
    filter_selected_items,
    parse_field_selector_input,
)
from fastedgy.orm.readable import is_guarded, unreadable_keys
from fastedgy.orm.row_selector import read_rows
from fastedgy.test.factories import create_user, create_workspace, use_request
from fastedgy.test.models.global_filter import GfArticle, GfDraft, GfLink, GfPrivateDoc


@contextmanager
def acting_as(workspace: Any, user: Any) -> Generator[None]:
    with use_request(user=user):
        context.set_workspace(workspace)

        yield


async def _links() -> SimpleNamespace:
    """A link to a doc of Ada's and a link to a doc of Bob's, in acme."""
    acme = await create_workspace(slug="acme")
    ada = await create_user(email="ada@example.io")
    bob = await create_user(email="bob@example.io")
    plan = await GfPrivateDoc(name="plan", owner=ada, workspace=acme).save()
    notes = await GfPrivateDoc(name="notes", owner=bob, workspace=acme).save()
    to_plan = await GfLink(label="to plan", doc=plan, workspace=acme).save()
    to_notes = await GfLink(label="to notes", doc=notes, workspace=acme).save()

    return SimpleNamespace(acme=acme, ada=ada, bob=bob, plan=plan, notes=notes, to_plan=to_plan, to_notes=to_notes)


def _selected(model_cls: Any, fields: str) -> Any:
    return apply_field_map_optimizations(
        model_cls.query.get_queryset(), parse_field_selector_input(model_cls, fields) or {}
    )


async def _read(link: GfLink) -> GfLink:
    return await _selected(GfLink, "label,doc.name").filter(id=link.id).get()


async def test_a_relation_the_request_may_not_read_keeps_its_key_alone(setup_db: FastEdgy) -> None:
    w = await _links()

    with acting_as(w.acme, w.bob):
        seen_by_bob = await filter_selected_fields(await _read(w.to_plan), "label,doc.name")

    with acting_as(w.acme, w.ada):
        seen_by_ada = await filter_selected_fields(await _read(w.to_plan), "label,doc.name")

    assert seen_by_bob == {"id": w.to_plan.id, "label": "to plan", "doc": {"id": w.plan.id}}
    assert seen_by_ada == {"id": w.to_plan.id, "label": "to plan", "doc": {"id": w.plan.id, "name": "plan"}}


async def test_a_page_is_narrowed_record_by_record(setup_db: FastEdgy) -> None:
    w = await _links()

    with acting_as(w.acme, w.bob):
        dumps = await filter_selected_items([await _read(w.to_plan), await _read(w.to_notes)], "label,doc.name")

    assert [dump["doc"] for dump in dumps] == [{"id": w.plan.id}, {"id": w.notes.id, "name": "notes"}]


async def test_a_read_answered_from_its_rows_is_narrowed_the_same_way(setup_db: FastEdgy) -> None:
    w = await _links()
    map_fields = parse_field_selector_input(GfLink, "label,doc.name") or {}

    with acting_as(w.acme, w.bob):
        reads, _seen = await read_rows(_selected(GfLink, "label,doc.name").order_by("id"), map_fields)

    assert [read["doc"] for read in reads] == [{"id": w.plan.id}, {"id": w.notes.id, "name": "notes"}]


async def test_a_relation_asked_for_its_key_alone_is_left_as_it_is(setup_db: FastEdgy) -> None:
    w = await _links()

    with acting_as(w.acme, w.bob):
        dump = await filter_selected_fields(await _read(w.to_plan), "label,doc")

    assert dump["doc"] == {"id": w.plan.id}


async def test_an_export_gives_nothing_of_a_record_the_request_may_not_read(setup_db: FastEdgy) -> None:
    w = await _links()

    with acting_as(w.acme, w.bob):
        response = await export_data(GfLink, "csv", fields="label,doc,doc.name", order_by="id")
        body = "".join(
            [chunk if isinstance(chunk, str) else bytes(chunk).decode() async for chunk in response.body_iterator]
        )

    rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))

    assert rows[1:] == [
        [str(w.to_plan.id), "to plan", str(w.plan.id), ""],
        [str(w.to_notes.id), "to notes", str(w.notes.id), "notes"],
    ]


async def test_a_reverse_relation_reads_through_the_related_model_query(setup_db: FastEdgy) -> None:
    acme = await create_workspace(slug="acme")
    ada = await create_user(email="ada@example.io")
    bob = await create_user(email="bob@example.io")
    article = await GfArticle(title="Roadmap", stock=1, workspace=acme).save()
    await GfDraft(body="outline", article=article, author=ada, workspace=acme).save()
    await GfDraft(body="summary", article=article, author=bob, workspace=acme).save()

    with acting_as(acme, bob):
        read = await _selected(GfArticle, "title,drafts.body").filter(id=article.id).get()
        dump = await filter_selected_fields(read, "title,drafts.body")

    assert [draft["body"] for draft in dump["drafts"]] == ["summary"]


async def test_only_a_model_read_narrower_than_its_scope_is_asked(setup_db: FastEdgy) -> None:
    w = await _links()

    with acting_as(w.acme, w.bob):
        docs = await unreadable_keys(GfPrivateDoc, [w.plan.id, w.notes.id, None])
        links = await unreadable_keys(GfLink, [w.to_plan.id, 0])

    assert not is_guarded(GfLink)
    assert docs == {w.plan.id}
    assert links == set()
