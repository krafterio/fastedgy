# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A filter path crosses a bounded number of relations, its sub-filters included.

A relation and its inverse lead back to where they started, so nothing ends a
path written ``workspace.workspace_users.workspace.workspace_users...``: every
hop is one more join, and only the settings say where it stops.
"""

import pytest

from fastedgy.app import FastEdgy
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.orm.filter import InvalidFilterError, R, filter_query


@pytest.fixture
def two_relations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_service(BaseSettings), "filter_max_depth", 2)


async def test_a_path_crossing_more_relations_than_allowed_is_refused(setup_db: FastEdgy, two_relations) -> None:
    from fastedgy.test.models.workspace_user import WorkspaceUser

    query = WorkspaceUser.global_query

    await filter_query(query, R("workspace.workspace_users.user", "=", 1), allow_excluded=True).all()

    with pytest.raises(InvalidFilterError, match="crosses 3 relations, more than 2"):
        filter_query(query, R("workspace.workspace_users.user.email", "=", "a@example.io"), allow_excluded=True)


async def test_the_relations_of_a_sub_filter_count_with_those_leading_to_it(setup_db: FastEdgy, two_relations) -> None:
    from fastedgy.test.models.workspace_user import WorkspaceUser

    query = WorkspaceUser.global_query

    await filter_query(query, R("workspace", "any", R("workspace_users.user", "=", 1)), allow_excluded=True).all()

    with pytest.raises(InvalidFilterError, match="crosses 3 relations"):
        filter_query(
            query,
            R("workspace", "any", R("workspace_users", "any", R("user.email", "=", "a@example.io"))),
            allow_excluded=True,
        )


def test_eight_relations_are_crossed_by_default() -> None:
    assert BaseSettings().filter_max_depth == 8
