# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel
from fastedgy.orm import Registry, fields
from fastedgy.orm.filter import R
from fastedgy.orm.registry import has_lazy_model

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User


logger = logging.getLogger("models.user_api_token")

# What of the secret stays readable after creation, enough for an owner to tell
# two keys apart in a list without the stored value granting access.
_HINT_LENGTH = 12

# One write per window: every authenticated call otherwise updates the same
# row, which SERIALIZABLE turns into contention on parallel calls.
_LAST_USED_WINDOW = timedelta(minutes=15)


def get_api_token_prefix() -> str:
    return get_service(BaseSettings).api_token_prefix


def generate_api_token() -> str:
    return get_api_token_prefix() + secrets.token_urlsafe(32)


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def api_token_hint(token: str) -> str:
    return token[:_HINT_LENGTH]


class UserApiTokenMixin(BaseModel):
    """A personal key giving a machine client durable access with the rights of
    its owner. Only the SHA-256 of the secret is stored: the full key is
    returned once, at creation, and never again."""

    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("API token")
        label_plural = _ts("API tokens")

    name: str = fields.CharField(max_length=255, label=_ts("Name"))

    user: "User | None" = fields.ForeignKey(
        "User",
        null=False,
        on_delete="CASCADE",
        # No reverse relation: a key is read and revoked through its own route,
        # never as a writable relation hanging off the user.
        related_name=False,
        label=_ts("User"),
    )

    token_hash: str = fields.CharField(max_length=64, unique=True, exclude=True, label=_ts("Fingerprint"))

    token_hint: str = fields.CharField(max_length=16, label=_ts("Preview"))

    expires_at: datetime | None = fields.DateTimeField(null=True, label=_ts("Expiration"))

    last_used_at: datetime | None = fields.DateTimeField(null=True, label=_ts("Last used"))


class BaseUserApiToken(UserApiTokenMixin):
    class Meta(UserApiTokenMixin.Meta):
        abstract = True


def register_default_user_api_token_model() -> None:
    """Declare the concrete model unless the app declared its own, the way an
    app opts out of any other framework model: by subclassing it first."""
    if has_lazy_model(UserApiTokenMixin):
        return

    class UserApiToken(BaseUserApiToken):
        class Meta:
            tablename = "user_api_tokens"
            label = _ts("API token")
            label_plural = _ts("API tokens")
            default_order_by = [("created_at", "desc")]


def find_user_api_token_model() -> type[UserApiTokenMixin] | None:
    """The concrete token model, or None where the app did not ask for personal
    API keys with `FastEdgy(user_api_tokens=True)`."""
    db_reg = get_service(Registry)

    for model in db_reg.models.values():
        if (
            isinstance(model, type)
            and issubclass(model, UserApiTokenMixin)
            and not getattr(model, "__is_proxy_model__", False)
            and not model.meta.abstract
        ):
            return cast(type[UserApiTokenMixin], model)

    return None


def get_user_api_token_model() -> type[UserApiTokenMixin]:
    model = find_user_api_token_model()

    if model is None:
        raise RuntimeError(
            "No UserApiToken model is registered: build the application with `FastEdgy(user_api_tokens=True)`."
        )

    return model


async def resolve_api_token(token: str) -> "User | None":
    """The user a raw API key designates, or None when it is unknown or
    expired. Reading it stamps `last_used_at`, at most once per window."""
    UserApiToken = find_user_api_token_model()

    if UserApiToken is None:
        return None

    # The fingerprint is an excluded column: a chained filter has to say so.
    # Through the unscoped manager, because this resolves who the caller is:
    # there is no user to scope by yet, and a realtime socket carries no request
    # for the scoped one to read a context from.
    record = (
        await UserApiToken.global_query.select_related("user")
        .filter(R("token_hash", "=", hash_api_token(token)), allow_excluded=True)
        .first()
    )
    user = getattr(record, "user", None) if record else None

    if not record or not user:
        return None

    now = datetime.now(UTC)
    expires_at = getattr(record, "expires_at", None)

    if expires_at is not None and expires_at <= now:
        return None

    last_used = getattr(record, "last_used_at", None)

    if last_used is None or now - last_used >= _LAST_USED_WINDOW:
        try:
            record.last_used_at = now
            await record.save()
        except Exception:
            logger.warning("Failed to stamp last_used_at on API token %s", getattr(record, "id", None), exc_info=True)

    return cast("User", user)


__all__ = [
    "BaseUserApiToken",
    "UserApiTokenMixin",
    "api_token_hint",
    "find_user_api_token_model",
    "generate_api_token",
    "get_api_token_prefix",
    "get_user_api_token_model",
    "hash_api_token",
    "register_default_user_api_token_model",
    "resolve_api_token",
]
