# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Personal API keys of the signed-in user.

Only the creation is written by hand, because the secret is derived server-side
and returned once and never again. Listing and deletion go through the generated
actions, so pagination, ordering, field selection, filters and the view
transformers behave exactly as on every other model.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from fastedgy.api_route_model.actions.delete_action import delete_item_action
from fastedgy.api_route_model.actions.list_action import list_items_action
from fastedgy.api_route_model.params import (
    FieldSelectorHeader,
    FilterHeader,
    OrderByQuery,
)
from fastedgy.api_route_model.types import ModelList
from fastedgy.depends.security import get_current_user
from fastedgy.http import Request
from fastedgy.i18n import _t
from fastedgy.models.user_api_token import (
    api_token_hint,
    generate_api_token,
    get_user_api_token_model,
    hash_api_token,
)
from fastedgy.orm import transaction
from fastedgy.orm.filter import R
from fastedgy.schemas.user_api_token import UserApiTokenCreate, UserApiTokenCreated


def create_user_api_tokens_router(prefix: str = "/user-api-tokens") -> APIRouter:
    """Built at wiring time, not at import: the concrete token model only
    exists once the registry is up."""
    UserApiToken = get_user_api_token_model()
    router = APIRouter(prefix=prefix, tags=["user_api_tokens"])

    def owned_by(user) -> Any:
        """The owner scope is what keeps a key personal: every route starts
        from here, never from the whole table."""
        return UserApiToken.query.filter(R("user", "=", user.id))

    @router.get("", response_model=ModelList[UserApiToken])
    async def list_user_api_tokens(
        request: Request,
        limit: int = Query(50, ge=0, le=1000),
        offset: int = Query(0, ge=0),
        order_by: str | None = OrderByQuery(),
        fields: str | None = FieldSelectorHeader(),
        filters: str | None = FilterHeader(),
        current_user=Depends(get_current_user),
    ):
        return await list_items_action(
            request,
            UserApiToken,
            query=owned_by(current_user),
            limit=limit,
            offset=offset,
            order_by=order_by,
            fields=fields,
            filters=filters,
        )

    @router.post("", status_code=status.HTTP_201_CREATED)
    @transaction
    async def create_user_api_token(
        data: UserApiTokenCreate,
        current_user=Depends(get_current_user),
    ) -> UserApiTokenCreated:
        secret = generate_api_token()
        token = UserApiToken(
            name=data.name.strip(),
            user=current_user,
            token_hash=hash_api_token(secret),
            token_hint=api_token_hint(secret),
            expires_at=data.expires_at,
        )
        await token.save()

        # Built from what the insert already holds: touching a field the
        # instance never loaded would lazy-load and blow up mid-transaction.
        return UserApiTokenCreated(
            id=getattr(token, "id", None) or 0,
            name=token.name,
            token_hint=token.token_hint,
            created_at=getattr(token, "created_at", None) or datetime.now(UTC),
            expires_at=data.expires_at,
            last_used_at=None,
            token=secret,
        )

    @router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_user_api_token(
        request: Request,
        token_id: int,
        current_user=Depends(get_current_user),
    ) -> None:
        await delete_item_action(
            request,
            UserApiToken,
            token_id,
            query=owned_by(current_user),
            not_found_message=_t("API token not found"),
        )

    return router


__all__ = [
    "create_user_api_tokens_router",
]
