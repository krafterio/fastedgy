# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A relation path only crosses the rows the request may read: those of the
current workspace, then what the global filters of each model let through."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.orm.filter import And, Or, R, filter_query
from fastedgy.test.factories import create_user, create_workspace, create_workspace_user, use_request
from fastedgy.test.models.global_filter import GfArticle, GfDraft
from fastedgy.test.models.workspace_user import WorkspaceUser

ELSEWHERE = R("user.workspace_memberships.workspace.slug", "=", "other")


@contextmanager
def acting_as(workspace: Any = None, user: Any = None) -> Generator[None]:
    with use_request(user=user):
        if workspace is not None:
            context.set_workspace(workspace)

        yield


async def _members() -> tuple[Any, Any, Any, Any]:
    """Ada and Bob, members of acme, Ada also a member of other."""
    acme = await create_workspace(slug="acme")
    other = await create_workspace(slug="other")
    ada = await create_user(email="ada@example.io")
    bob = await create_user(email="bob@example.io")
    ada_in_acme = await create_workspace_user(ada, acme)
    bob_in_acme = await create_workspace_user(bob, acme)
    await create_workspace_user(ada, other)

    return acme, bob, ada_in_acme, bob_in_acme


async def _members_of(workspace: Any, rule: Any) -> set[int]:
    rows = await WorkspaceUser.query.filter(R("workspace", "=", workspace.id), rule).all()

    return {row.id for row in rows}


async def test_a_path_crosses_only_the_rows_of_the_current_workspace(setup_db: FastEdgy) -> None:
    acme, bob, _ada_in_acme, _bob_in_acme = await _members()

    with acting_as(acme, bob):
        crossed = await _members_of(acme, ELSEWHERE)
        through_the_manager = await filter_query(
            WorkspaceUser.query, And(R("workspace", "=", acme.id), ELSEWHERE)
        ).all()
        own = await _members_of(acme, R("user.workspace_memberships.workspace.slug", "=", "acme"))

    assert crossed == set()
    assert through_the_manager == []
    assert len(own) == 2


async def test_an_or_branch_and_an_any_block_cross_the_same_rows(setup_db: FastEdgy) -> None:
    acme, bob, _ada_in_acme, _bob_in_acme = await _members()

    with acting_as(acme, bob):
        either = await _members_of(acme, Or(ELSEWHERE, R("id", "=", 0)))
        any_of = await _members_of(acme, R("user.workspace_memberships", "any", R("workspace.slug", "=", "other")))

    assert either == set()
    assert any_of == set()


async def test_an_ordering_aggregates_only_the_readable_rows(setup_db: FastEdgy) -> None:
    acme, bob, ada_in_acme, bob_in_acme = await _members()

    with acting_as(acme, bob):
        rows = (
            await WorkspaceUser.query.filter(R("workspace", "=", acme.id))
            .order_by("-user__workspace_memberships__workspace__slug", "-id")
            .all()
        )

    assert [row.id for row in rows] == [bob_in_acme.id, ada_in_acme.id]


async def test_a_path_crosses_only_the_rows_the_global_filters_let_through(setup_db: FastEdgy) -> None:
    acme = await create_workspace(slug="acme")
    ada = await create_user(email="ada@example.io")
    bob = await create_user(email="bob@example.io")
    article = GfArticle(title="Roadmap", stock=1, workspace=acme)
    await article.save()
    await GfDraft(body="outline", article=article, author=ada, workspace=acme).save()
    drafted = R("drafts.body", "=", "outline")

    with acting_as(acme, bob):
        seen_by_bob = await GfArticle.query.filter(drafted).all()

    with acting_as(acme, ada):
        seen_by_ada = await GfArticle.query.filter(drafted).all()

    assert seen_by_bob == []
    assert [row.id for row in seen_by_ada] == [article.id]


async def test_the_system_crosses_every_row(setup_db: FastEdgy) -> None:
    acme, bob, ada_in_acme, _bob_in_acme = await _members()

    with acting_as(acme, bob):
        global_rows = await WorkspaceUser.global_query.filter(ELSEWHERE).all()
        trusted_rows = await WorkspaceUser.query.filter(ELSEWHERE, allow_excluded=True).all()

    with acting_as(user=bob):
        outside_any_workspace = await WorkspaceUser.query.filter(ELSEWHERE).all()

    assert ada_in_acme.id in {row.id for row in global_rows}
    assert ada_in_acme.id in {row.id for row in trusted_rows}
    assert ada_in_acme.id in {row.id for row in outside_any_workspace}
