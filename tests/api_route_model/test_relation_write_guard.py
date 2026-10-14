# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Relation-input guard: a payload cannot do to a related model what the API
forbids on it directly. Comment disables create/patch/delete: its records are
unreachable through relation operations — including link-level operations,
which re-point the foreign key stored on the target records."""

import httpx

from .helpers import make_product


async def test_a_nested_write_runs_the_related_models_transformers(auth_http: httpx.AsyncClient) -> None:
    """A create, update or delete reaching a related record through a relation runs
    that model's save transformers, so its own authorization applies as on a direct
    write. A model without transformers is written as before."""
    from fastapi import HTTPException

    from fastedgy.api_route_model.registry import ViewTransformerRegistry
    from fastedgy.api_route_model.view_transformer import PreSaveTransformer
    from fastedgy.dependencies import get_service
    from fastedgy.test.models.note import Note

    class _RejectBlocked(PreSaveTransformer):
        async def pre_save(self, request, item, item_data, ctx, created) -> None:
            if getattr(item, "content", None) == "blocked":
                raise HTTPException(status_code=403, detail="nope")

    registry = get_service(ViewTransformerRegistry)
    registry.register_transformer(_RejectBlocked, Note)
    try:
        product = await make_product(auth_http)
        blocked = await auth_http.patch(
            f"/api/test_products/{product['id']}", json={"notes": [["create", {"content": "blocked"}]]}
        )
        allowed = await auth_http.patch(
            f"/api/test_products/{product['id']}", json={"notes": [["create", {"content": "ok"}]]}
        )

        assert blocked.status_code == 403, blocked.text
        assert allowed.status_code == 200, allowed.text
    finally:
        registry._transformers[Note] = [
            t for t in registry._transformers.get(Note, []) if not isinstance(t, _RejectBlocked)
        ]


async def _make_comment(content: str = "hello"):
    from fastedgy.test.models.comment import Comment

    return await Comment.query.create(content=content)


async def test_o2m_record_operations_are_denied(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.comment import Comment

    product = await make_product(auth_http)
    comment = await _make_comment()

    for operations in (
        [["create", {"content": "new"}]],
        [["update", {"id": comment.id, "content": "x"}]],
        [["delete", comment.id]],
    ):
        response = await auth_http.patch(
            f"/api/test_products/{product['id']}",
            json={"comments": operations},
        )

        assert response.status_code == 403, response.text

    assert await Comment.query.filter(id=comment.id).get_or_none() is not None


def test_forward_fk_record_ops_are_denied_on_an_unexposed_model() -> None:
    """A forward foreign key does not create, update or delete the record it points
    at when the model is not registered for writing (``deny_unregistered``), while
    the reverse/m2m path keeps managing its own children through their parent."""
    import pytest
    from fastapi import HTTPException

    from fastedgy.api_route_model.action.relations import ensure_relation_write_allowed
    from fastedgy.test.models.assignment import Assignment

    for op in ("create", "update", "delete"):
        with pytest.raises(HTTPException) as raised:
            ensure_relation_write_allowed(Assignment, {op}, "anchor", deny_unregistered=True)
        assert raised.value.status_code == 403

    ensure_relation_write_allowed(Assignment, {"update"}, "assignments")
    ensure_relation_write_allowed(Assignment, set(), "anchor", deny_unregistered=True)


async def test_o2m_link_operations_count_as_target_updates(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.comment import Comment

    product = await make_product(auth_http)
    comment = await _make_comment()

    response = await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"comments": [["link", comment.id]]},
    )

    assert response.status_code == 403
    linked = await Comment.query.filter(id=comment.id).get()
    assert getattr(getattr(linked, "product", None), "id", None) is None
