# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A relation path that comes back to the table it started from.

``workspace.workspace_users.user.id`` on the membership model is the shape every
"the workspaces I belong to" scope takes: up to the parent, back down its
collection of memberships. The subquery then names ``workspace_users`` a second
time, and unaliased that occurrence shadows the outer row: the correlation
compares the inner row to itself, so the EXISTS asks "is there any membership for
this user at all" and answers yes for every row. The filter silently stops
filtering, which on an access-control scope means every workspace's memberships
come back.
"""

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import R, filter_query
from fastedgy.test.factories import create_user


async def _membership(workspace_id: int | None, user_id: int | None):
    from fastedgy.test.models.workspace_user import WorkspaceUser

    membership = WorkspaceUser(workspace=workspace_id, user=user_id)
    membership.apply_readonly_values({"workspace": workspace_id, "user": user_id})

    return await membership.save()


async def test_path_returning_to_its_own_table_still_scopes(setup_db: FastEdgy) -> None:
    from fastedgy.test.models.workspace import Workspace
    from fastedgy.test.models.workspace_user import WorkspaceUser

    mine = await Workspace(slug="mine").save()
    other = await Workspace(slug="other").save()

    alice = await create_user(email="alice@example.io")
    bob = await create_user(email="bob@example.io")
    carol = await create_user(email="carol@example.io")

    await _membership(mine.id, alice.id)
    await _membership(mine.id, bob.id)
    await _membership(other.id, carol.id)

    rows = await filter_query(
        WorkspaceUser.global_query,
        R("workspace.workspace_users.user.id", "=", alice.id),
        allow_excluded=True,
    ).all()

    assert {row.user.id for row in rows} == {alice.id, bob.id}
