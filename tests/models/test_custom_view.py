# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.models.custom_view import get_custom_view_model
from fastedgy.models.custom_view_favorite import find_custom_view_favorite_model
from fastedgy.test.factories import authenticate, create_user, create_workspace, use_request


@contextmanager
def acting_as(user: Any, workspace: Any = None) -> Generator[None]:
    with use_request(user=user):
        context.set_workspace(workspace)

        yield


async def _view(name: str = "Open", **values: Any) -> Any:
    view = get_custom_view_model()(name=name, model="product", **values)
    await view.save()

    return view


async def _names() -> set[str]:
    return {view.name for view in await get_custom_view_model().query.all()}


async def test_a_view_belongs_to_the_workspace_it_is_saved_in(setup_db: FastEdgy) -> None:
    acme, other = await create_workspace(slug="acme"), await create_workspace(slug="other")
    user = await create_user(email="u@example.io")

    with acting_as(user, acme):
        await _view("In acme")

    with acting_as(user):
        await _view("Global")

    with acting_as(user, acme):
        assert await _names() == {"In acme"}

    with acting_as(user, other):
        assert await _names() == set()

    with acting_as(user):
        assert await _names() == {"Global"}


async def test_a_private_view_is_its_owner_alone(setup_db: FastEdgy) -> None:
    acme = await create_workspace(slug="acme")
    owner, other = await create_user(email="o@example.io"), await create_user(email="x@example.io")

    with acting_as(owner, acme):
        await _view("Mine", user=owner)
        await _view("Ours")

    with acting_as(other, acme):
        assert await _names() == {"Ours"}

    with acting_as(owner, acme):
        assert await _names() == {"Mine", "Ours"}


async def test_a_view_is_never_given_to_another_user(setup_db: FastEdgy) -> None:
    owner, other = await create_user(email="o@example.io"), await create_user(email="x@example.io")

    with acting_as(owner), pytest.raises(HTTPException) as refused:
        await _view("Theirs", user=other)

    assert refused.value.status_code == 403


async def test_a_name_is_unique_within_what_a_list_shows(setup_db: FastEdgy) -> None:
    acme, other = await create_workspace(slug="acme"), await create_workspace(slug="other")
    owner, colleague = await create_user(email="o@example.io"), await create_user(email="c@example.io")

    with acting_as(owner, acme):
        await _view("Open")

        for values in ({}, {"user": owner}):
            with pytest.raises(HTTPException) as refused:
                await _view("Open", **values)

            assert refused.value.status_code == 422

        await _view("Open", scope="archive")
        await _view("Mine", user=owner)

    with acting_as(colleague, acme):
        await _view("Mine", user=colleague)

    with acting_as(owner, other):
        await _view("Open")

    with acting_as(owner):
        await _view("Open")


async def test_a_list_has_one_default_and_never_a_private_one(setup_db: FastEdgy) -> None:
    acme = await create_workspace(slug="acme")
    user = await create_user(email="u@example.io")

    with acting_as(user, acme):
        first = await _view("First", is_default=True)
        second = await _view("Second", is_default=True)
        elsewhere = await _view("Elsewhere", scope="archive", is_default=True)

        with pytest.raises(HTTPException) as refused:
            await _view("Mine", user=user, is_default=True)

        defaults = {view.id for view in await get_custom_view_model().query.all() if view.is_default}

    assert refused.value.status_code == 422
    assert defaults == {second.id, elsewhere.id}
    assert first.id not in defaults


async def test_a_view_lists_a_described_model(setup_db: FastEdgy) -> None:
    user = await create_user(email="u@example.io")

    with acting_as(user), pytest.raises(HTTPException) as refused:
        await get_custom_view_model()(name="Ghost", model="nowhere").save()

    assert refused.value.status_code == 422


async def test_the_shared_views_follow_who_manages_them(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    CustomView = get_custom_view_model()
    user = await create_user(email="u@example.io")

    with acting_as(user):
        shared = await _view("Shared")
        private = await _view("Private", user=user)

    monkeypatch.setattr(CustomView, "can_manage_shared", classmethod(lambda cls: False))

    with acting_as(user):
        for action in (lambda: _view("Another"), lambda: _rename(shared, "Renamed"), lambda: shared.delete()):
            with pytest.raises(HTTPException) as refused:
                await action()

            assert refused.value.status_code == 403

        await _rename(private, "Still mine")

        assert shared.editable is False
        assert private.editable is True


async def _rename(view: Any, name: str) -> None:
    view.name = name
    await view.save()


async def test_a_user_has_one_favorite_per_list(setup_db: FastEdgy) -> None:
    Favorite = find_custom_view_favorite_model()
    assert Favorite is not None
    acme = await create_workspace(slug="acme")
    user, colleague = await create_user(email="u@example.io"), await create_user(email="c@example.io")

    with acting_as(user, acme):
        first, second = await _view("First"), await _view("Second")
        archived = await _view("Archived", scope="archive")

        for view in (first, second, archived):
            await Favorite(view=view).save()

        mine = {(favorite.view.id, favorite.user.id) for favorite in await Favorite.query.all()}

    with acting_as(colleague, acme):
        await Favorite(view=first).save()
        theirs = {favorite.view.id for favorite in await Favorite.query.all()}

    assert mine == {(second.id, user.id), (archived.id, user.id)}
    assert theirs == {first.id}


async def test_a_favorite_is_read_in_the_workspace_of_its_view(setup_db: FastEdgy) -> None:
    Favorite = find_custom_view_favorite_model()
    assert Favorite is not None
    acme, other = await create_workspace(slug="acme"), await create_workspace(slug="other")
    user = await create_user(email="u@example.io")

    with acting_as(user, acme):
        in_acme = await _view("In acme")
        await Favorite(view=in_acme).save()

    with acting_as(user, other):
        in_other = await _view("In other")
        await Favorite(view=in_other).save()
        seen_in_other = {favorite.view.id for favorite in await Favorite.query.all()}

    with acting_as(user, acme):
        seen_in_acme = {favorite.view.id for favorite in await Favorite.query.all()}

    assert seen_in_acme == {in_acme.id}
    assert seen_in_other == {in_other.id}


async def test_the_routes_serve_the_global_views(setup_http: httpx.AsyncClient) -> None:
    user = await create_user(email="u@example.io")
    client = authenticate(setup_http, user)

    created = await client.post(
        "/api/custom_views",
        json={"name": "Expensive", "model": "product", "filters": ["price", ">", 100], "order_by": ["price:desc"]},
    )

    assert created.status_code == 200, created.text

    listed = await client.get("/api/custom_views", headers={"X-Fields": "id,name,filters,editable,user"})

    assert listed.status_code == 200, listed.text
    assert [(item["name"], item["filters"], item["editable"]) for item in listed.json()["items"]] == [
        ("Expensive", ["price", ">", 100], True)
    ]

    favorite = await client.post("/api/custom_view_favorites", json={"view": created.json()["id"]})

    assert favorite.status_code == 200, favorite.text
    assert (await client.get("/api/custom_view_favorites", headers={"X-Fields": "id,user"})).json()["items"] == [
        {"id": favorite.json()["id"], "user": {"id": user.id}}
    ]


async def test_a_list_opens_on_the_favorite_of_its_user_or_of_everyone(setup_http: httpx.AsyncClient) -> None:
    user = await create_user(email="u@example.io")
    client = authenticate(setup_http, user)
    ids = {}

    for name, values in (("Everyone", {"is_default": True}), ("Mine", {}), ("Other", {})):
        response = await client.post("/api/custom_views", json={"name": name, "model": "product", **values})
        ids[name] = response.json()["id"]

    await client.post("/api/custom_view_favorites", json={"view": ids["Mine"]})

    opening = await client.get(
        "/api/custom_views",
        headers={
            "X-Fields": "id,name",
            "X-Filter": json.dumps(["|", [["is_default", "is true"], ["favorites.user", "=", user.id]]]),
        },
    )

    assert opening.status_code == 200, opening.text
    assert sorted(item["name"] for item in opening.json()["items"]) == ["Everyone", "Mine"]
