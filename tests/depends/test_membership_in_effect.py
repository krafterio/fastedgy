# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The memberships in effect, the rule an application gives its membership
model: the same ones open their workspace whatever reads it, a route, the
default workspace, a socket or the list of the account."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException

from fastedgy import context
from fastedgy.api.account_workspaces import account_memberships
from fastedgy.app import FastEdgy
from fastedgy.depends.security import get_current_workspace
from fastedgy.http import Request
from fastedgy.orm.filter import R
from fastedgy.realtime.auth import held_scopes, scope_of, scopes_of
from fastedgy.test.factories import create_user, create_workspace, create_workspace_user
from fastedgy.test.models.workspace_user import WorkspaceUser


@pytest.fixture
def beta_out_of_effect(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(WorkspaceUser, "effective_rule", classmethod(lambda cls: R("workspace.slug", "!=", "beta")))

    yield


async def _member_of_acme_and_beta() -> tuple[Any, Any, Any]:
    user = await create_user(email="ada@example.io")
    acme = await create_workspace(slug="acme", name="Acme")
    beta = await create_workspace(slug="beta", name="Beta")
    await create_workspace_user(user, acme)
    await create_workspace_user(user, beta)

    return user, acme, beta


def _request_under(slug: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/{slug}/products",
            "query_string": b"",
            "headers": [],
            "path_params": {"workspace": slug},
        }
    )


async def test_a_route_opens_only_a_workspace_of_a_membership_in_effect(
    setup_db: FastEdgy, beta_out_of_effect: None
) -> None:
    user, _acme, _beta = await _member_of_acme_and_beta()

    for slug, opens in (("acme", True), ("beta", False)):
        token = context.set_request(_request_under(slug))

        try:
            if opens:
                assert getattr(await get_current_workspace(current_user=user), "slug", None) == slug
            else:
                with pytest.raises(HTTPException) as refused:
                    await get_current_workspace(current_user=user)

                assert refused.value.status_code == 404
        finally:
            context.reset_request(token)


async def test_the_default_workspace_is_one_of_a_membership_in_effect(
    setup_db: FastEdgy, beta_out_of_effect: None
) -> None:
    user, _acme, beta = await _member_of_acme_and_beta()
    marked = await WorkspaceUser.global_query.filter(R("workspace", "=", beta.id)).first()
    assert marked is not None
    await marked.make_default()

    landing = await WorkspaceUser.default_for(user.id)

    assert getattr(getattr(landing, "workspace", None), "slug", None) == "acme"


async def test_a_socket_reaches_only_the_workspaces_of_memberships_in_effect(
    setup_db: FastEdgy, beta_out_of_effect: None
) -> None:
    user, acme, beta = await _member_of_acme_and_beta()

    assert getattr(await scope_of(user, "acme"), "slug", None) == "acme"
    assert await scope_of(user, "beta") is None
    assert [scope.slug for scope in await scopes_of(user, ["acme", "beta"])] == ["acme"]
    assert await held_scopes(user, [acme.id, beta.id]) == {acme.id}


async def test_the_list_of_the_account_holds_only_the_memberships_in_effect(
    setup_db: FastEdgy, beta_out_of_effect: None
) -> None:
    user, _acme, _beta = await _member_of_acme_and_beta()

    memberships = await account_memberships(user).select_related("workspace").all()

    assert [membership.workspace.slug for membership in memberships] == ["acme"]


async def test_every_membership_is_in_effect_by_default(setup_db: FastEdgy) -> None:
    user, acme, beta = await _member_of_acme_and_beta()

    assert await held_scopes(user, [acme.id, beta.id]) == {acme.id, beta.id}
