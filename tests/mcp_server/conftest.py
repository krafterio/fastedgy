# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
import pytest

from tests.mcp_server.helpers import create_token

# The MCP server ships behind the `mcp` extra: without it there is nothing here
# to test.
pytest.importorskip("mcp.server", reason="install fastedgy[mcp]")


@pytest.fixture
async def workspace_env(setup_db):
    """A user with one membership: every model tool takes a workspace slug."""
    from fastedgy.test.factories import create_user, create_workspace, create_workspace_user

    user = await create_user(email="agent@example.io")
    workspace = await create_workspace(slug="acme", name="Acme")
    await create_workspace_user(user, workspace)

    return user, workspace


@pytest.fixture
async def agent(setup_http: httpx.AsyncClient, workspace_env) -> tuple[httpx.AsyncClient, str, str]:
    """An HTTP client holding an API key and nothing else: the JWT that minted
    the key is dropped, so every call goes through the key itself."""
    from fastedgy.test.factories import authenticate

    user, workspace = workspace_env
    token = await create_token(authenticate(setup_http, user))
    setup_http.headers.pop("Authorization", None)

    return setup_http, token, workspace.slug
