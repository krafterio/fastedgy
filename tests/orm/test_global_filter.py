# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Generator
from contextlib import contextmanager

import pytest

from fastapi import HTTPException

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.orm.filter import GlobalFilterRegistry
from fastedgy.test.factories import create_user, create_workspace, use_request
from fastedgy.test.models.global_filter import GfArticle, GfLink, GfPrivateDoc, GfSharedDoc


@contextmanager
def acting_as(workspace=None, user=None) -> Generator[None]:
    with use_request(user=user):
        if workspace is not None:
            context.set_workspace(workspace)

        yield


async def _seed_workspaces_and_users():
    ws1 = await create_workspace(slug="ws1")
    ws2 = await create_workspace(slug="ws2")
    u1 = await create_user(email="u1@example.io")
    u2 = await create_user(email="u2@example.io")

    return ws1, ws2, u1, u2


async def test_direct_and_stacked_filters_are_applied(setup_db: FastEdgy) -> None:
    ws1, _ws2, u1, _u2 = await _seed_workspaces_and_users()

    await GfArticle(title="visible", is_active=True, stock=5, workspace=ws1).save()
    await GfArticle(title="inactive", is_active=False, stock=5, workspace=ws1).save()
    await GfArticle(title="out_of_stock", is_active=True, stock=0, workspace=ws1).save()

    with acting_as(ws1, u1):
        rows = await GfArticle.query.all()

    assert {row.title for row in rows} == {"visible"}


async def test_workspace_scoping_across_two_workspaces(setup_db: FastEdgy) -> None:
    ws1, ws2, u1, u2 = await _seed_workspaces_and_users()

    await GfArticle(title="article_ws1", is_active=True, stock=5, workspace=ws1).save()
    await GfArticle(title="article_ws2", is_active=True, stock=5, workspace=ws2).save()

    with acting_as(ws1, u1):
        rows_ws1 = await GfArticle.query.all()

    with acting_as(ws2, u2):
        rows_ws2 = await GfArticle.query.all()

    assert {row.title for row in rows_ws1} == {"article_ws1"}
    assert {row.title for row in rows_ws2} == {"article_ws2"}


async def test_global_query_bypasses_workspace_and_global_filters(setup_db: FastEdgy) -> None:
    ws1, ws2, _u1, _u2 = await _seed_workspaces_and_users()

    await GfArticle(title="visible_ws1", is_active=True, stock=5, workspace=ws1).save()
    await GfArticle(title="filtered_ws2", is_active=False, stock=0, workspace=ws2).save()

    rows = await GfArticle.global_query.all()

    assert {row.title for row in rows} == {"visible_ws1", "filtered_ws2"}


async def test_mixin_inherited_filter_scopes_to_current_user(setup_db: FastEdgy) -> None:
    ws1, _ws2, u1, u2 = await _seed_workspaces_and_users()

    await GfPrivateDoc(name="owned_by_u1", owner=u1, workspace=ws1).save()
    await GfPrivateDoc(name="owned_by_u2", owner=u2, workspace=ws1).save()

    with acting_as(ws1, u1):
        rows = await GfPrivateDoc.query.all()

    assert {row.name for row in rows} == {"owned_by_u1"}


async def test_apply_predicate_exempts_the_shared_model(setup_db: FastEdgy) -> None:
    ws1, _ws2, u1, u2 = await _seed_workspaces_and_users()

    await GfSharedDoc(name="shared_by_u1", owner=u1, workspace=ws1).save()
    await GfSharedDoc(name="shared_by_u2", owner=u2, workspace=ws1).save()

    with acting_as(ws1, u1):
        rows = await GfSharedDoc.query.all()

    assert {row.name for row in rows} == {"shared_by_u1", "shared_by_u2"}


async def test_none_filter_is_a_noop_without_a_user(setup_db: FastEdgy) -> None:
    ws1, _ws2, u1, u2 = await _seed_workspaces_and_users()

    await GfPrivateDoc(name="owned_by_u1", owner=u1, workspace=ws1).save()
    await GfPrivateDoc(name="owned_by_u2", owner=u2, workspace=ws1).save()

    with acting_as(ws1, user=None):
        rows = await GfPrivateDoc.query.all()

    assert {row.name for row in rows} == {"owned_by_u1", "owned_by_u2"}


async def test_save_rejects_reference_to_an_inaccessible_record(setup_db: FastEdgy) -> None:
    ws1, _ws2, u1, u2 = await _seed_workspaces_and_users()

    own_doc = GfPrivateDoc(name="own", owner=u1, workspace=ws1)
    await own_doc.save()
    other_doc = GfPrivateDoc(name="other", owner=u2, workspace=ws1)
    await other_doc.save()

    with acting_as(ws1, u1):
        await GfLink(doc=own_doc, workspace=ws1).save()

        with pytest.raises(HTTPException) as exc:
            await GfLink(doc=other_doc, workspace=ws1).save()

    assert exc.value.status_code == 403


async def test_save_validates_only_changed_references(setup_db: FastEdgy) -> None:
    ws1, _ws2, u1, u2 = await _seed_workspaces_and_users()

    other_doc = GfPrivateDoc(name="other", owner=u2, workspace=ws1)
    await other_doc.save()
    other_doc2 = GfPrivateDoc(name="other2", owner=u2, workspace=ws1)
    await other_doc2.save()
    link = GfLink(label="x", doc=other_doc, workspace=ws1)
    await link.save()

    with acting_as(ws1, u1):
        loaded = await GfLink.global_query.get(id=link.id)

        loaded.label = "y"
        await loaded.save()

        loaded.doc = other_doc2

        with pytest.raises(HTTPException) as exc:
            await loaded.save()

    assert exc.value.status_code == 403


async def test_save_skips_reference_validation_without_a_user(setup_db: FastEdgy) -> None:
    ws1, _ws2, _u1, u2 = await _seed_workspaces_and_users()

    other_doc = GfPrivateDoc(name="other", owner=u2, workspace=ws1)
    await other_doc.save()

    link = GfLink(doc=other_doc, workspace=ws1)
    await link.save()

    assert link.id is not None


async def test_registry_is_a_di_singleton_collecting_via_mro(setup_app: FastEdgy) -> None:
    registry = get_service(GlobalFilterRegistry)

    assert registry is get_service(GlobalFilterRegistry)
    assert len(registry.get_filters(WorkspaceableMixin)) == 1
    assert len(registry.get_filters(GfArticle)) == 3
    assert len(registry.get_filters(GfPrivateDoc)) == 2
    assert registry.has_filters(GfSharedDoc)
