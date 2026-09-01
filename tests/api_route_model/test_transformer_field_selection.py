# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""What a view transformer is told about the fields the read asked for.

A transformer enriches a payload after the fact, and each key it adds usually
costs a query per row. Without knowing what was selected it pays for all of
them on every read, a sync manifest asking for `id,updated_at` included.
"""

from typing import Any

import httpx
import pytest

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import GetViewTransformer
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.orm.field_selector import selection_includes
from fastedgy.test.models.category import Category


class _SelectionRecordingTransformer(GetViewTransformer[Category]):
    """Records what each action handed it, and enriches only when asked."""

    seen: list[Any] = []

    async def get_view(
        self,
        request: Request,
        item: Category,
        item_dump: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        type(self).seen.append(ctx.get("fields"))

        if selection_includes(ctx.get("fields"), "extra_count"):
            item_dump["extra_count"] = 1

        return item_dump


def _register() -> None:
    _SelectionRecordingTransformer.seen = []
    get_service(ViewTransformerRegistry).register_transformer(_SelectionRecordingTransformer, Category)


def _cleanup_transformers() -> None:
    ViewTransformerRegistry._transformers.pop(Category, None)


@pytest.fixture(autouse=True)
def _isolated_registry():
    _cleanup_transformers()
    yield
    _cleanup_transformers()


def test_selection_includes_with_nothing_selected() -> None:
    assert selection_includes(None, "member_count") is True
    assert selection_includes("", "member_count") is True


def test_selection_includes_with_the_wildcard() -> None:
    assert selection_includes("+", "member_count") is True
    assert selection_includes("id,+", "member_count") is True


def test_selection_includes_only_what_was_named() -> None:
    assert selection_includes("id,member_count", "member_count") is True
    assert selection_includes("id, member_count ", "member_count") is True
    assert selection_includes("id,updated_at", "member_count") is False
    assert selection_includes(["id", "updated_at"], "member_count") is False


def test_selection_includes_any_of_several_names() -> None:
    assert selection_includes("id,notes_count", "flows_count", "notes_count") is True
    assert selection_includes("id,name", "flows_count", "notes_count") is False


def test_selection_ignores_a_name_that_only_appears_as_a_relation_path() -> None:
    # `project.flows_count` is the nested project's key, not this record's.
    assert selection_includes("id,project.flows_count", "flows_count") is False


async def test_list_hands_the_selection_to_the_transformer(auth_http: httpx.AsyncClient) -> None:
    _register()
    await auth_http.post("/api/test_categories", json={"name": "Books"})

    payload = (await auth_http.get("/api/test_categories", headers={"X-Fields": "id,updated_at"})).json()

    # The create above went through it too, so the read is the last entry.
    assert _SelectionRecordingTransformer.seen[-1] == "id,updated_at"
    assert "extra_count" not in payload["items"][0]


async def test_list_enriches_when_the_key_is_selected(auth_http: httpx.AsyncClient) -> None:
    _register()
    await auth_http.post("/api/test_categories", json={"name": "Books"})

    payload = (await auth_http.get("/api/test_categories", headers={"X-Fields": "id,extra_count"})).json()

    assert payload["items"][0]["extra_count"] == 1


async def test_list_without_a_selection_enriches_everything(auth_http: httpx.AsyncClient) -> None:
    _register()
    await auth_http.post("/api/test_categories", json={"name": "Books"})

    payload = (await auth_http.get("/api/test_categories")).json()

    assert _SelectionRecordingTransformer.seen[-1] is None
    assert payload["items"][0]["extra_count"] == 1


async def test_get_hands_the_selection_to_the_transformer(auth_http: httpx.AsyncClient) -> None:
    _register()
    created = (await auth_http.post("/api/test_categories", json={"name": "Books"})).json()

    payload = (
        await auth_http.get(f"/api/test_categories/{created['id']}", headers={"X-Fields": "id,updated_at"})
    ).json()

    assert _SelectionRecordingTransformer.seen[-1] == "id,updated_at"
    assert "extra_count" not in payload
