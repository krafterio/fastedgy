# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from anyio import CapacityLimiter, to_thread
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt

from fastedgy import context
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.depends.hasher import get_hasher_registry
from fastedgy.models.user_api_token import resolve_api_token
from fastedgy.orm import Registry

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace
    from fastedgy.models.workspace_user import BaseWorkspaceUser as WorkspaceUser


logger = logging.getLogger("fastedgy.security")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# Hosts that reserve `Authorization` for their own OAuth token still let the
# user set one extra header: an API key travels there instead. The name is one
# of those Claude's connector dialog offers.
API_TOKEN_HEADER = "X-Api-Token"
api_token_scheme = APIKeyHeader(name=API_TOKEN_HEADER, auto_error=False)


# Hashing is CPU-bound and, with argon2id, holds its memory cost for the whole
# call. Beyond one hash per core there is nothing to gain and a footprint to
# pay, so the threads are bounded here rather than left to anyio's default of
# 40 per loop: 8 concurrent argon2id hashes are 152 MiB, 40 would be 760 MiB
# per worker process.
_hash_limiter = CapacityLimiter(8)


def hash_password(password: str) -> str:
    return get_hasher_registry().hash(password)


def verify_password(password: str | None, verify_password: str | None) -> bool:
    """``password`` is the stored hash, ``verify_password`` the clear candidate.

    The scheme is chosen from the stored hash's own prefix, so a base holding
    both bcrypt and argon2id keeps working.
    """
    return get_hasher_registry().verify(verify_password, password)


async def hash_password_async(password: str) -> str:
    """Hash in a worker thread rather than on the event loop.

    A KDF costs tens to hundreds of milliseconds of CPU by design, and a
    synchronous call freezes every other request served by the same uvicorn
    worker for that whole time. The thread does not make it cheaper, it makes
    it concurrent: argon2 and bcrypt both release the GIL.
    """
    return await to_thread.run_sync(hash_password, password, limiter=_hash_limiter)


async def verify_password_async(password: str | None, plain_password: str | None) -> bool:
    """Same reason as :func:`hash_password_async`: verifying costs as much as
    hashing, and it runs on every login.
    """
    return await to_thread.run_sync(verify_password, password, plain_password, limiter=_hash_limiter)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    settings = get_service(BaseSettings)
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.auth_access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm)
    return encoded_jwt


def create_refresh_token(data: dict):
    settings = get_service(BaseSettings)
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.auth_refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm)
    return encoded_jwt


async def authenticate_user(email: str, password: str):
    db_reg = get_service(Registry)
    User = cast(type["User"], db_reg.get_model("User"))

    if hasattr(User, "username") or "username" in User.model_fields:
        user = await User.query.filter((User.columns.email == email) | (User.columns.username == email)).first()
    else:
        user = await User.query.filter(email=email).first()

    if not user or not await verify_password_async(user.password, password):
        return False

    await rehash_password_if_needed(user, password)

    return user


async def rehash_password_if_needed(user: "User", raw_password: str) -> None:
    """Upgrade a hash left over from an older scheme, on the login that proved
    the password.

    This is what migrates a base off bcrypt without asking anyone to reset
    anything. Only the password column is written, and a failure here must
    never turn a valid login into an error.
    """
    if not get_hasher_registry().needs_rehash(user.password):
        return

    try:
        user.password = await hash_password_async(raw_password)
        await user.save(values={"password": user.password})
    except Exception:
        logger.exception(f"Could not upgrade the password hash of user {user.pk}")


async def get_current_user(
    token: str | None = Depends(oauth2_scheme_optional),
    api_token: str | None = Depends(api_token_scheme),
) -> "User":
    user = context.get_user()
    if user:
        return user

    settings = get_service(BaseSettings)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = token or api_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # A personal API key stands in for a JWT everywhere a bearer is read, so a
    # machine client reaches every route the user reaches, and no entry point
    # has to resolve credentials by hand.
    if settings.api_token_prefix and token.startswith(settings.api_token_prefix):
        user = await resolve_api_token(token)

        if user is None:
            raise credentials_exception

        context.set_user(user)

        return user

    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])
        email: str = str(payload.get("sub"))
        token_type: str = str(payload.get("type"))

        if email is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    db_reg = get_service(Registry)
    User = cast(type["User"], db_reg.get_model("User"))

    if hasattr(User, "username") or "username" in User.model_fields:
        user = await User.query.filter((User.columns.email == email) | (User.columns.username == email)).first()
    else:
        user = await User.query.filter(email=email).first()

    if user is None:
        raise credentials_exception

    context.set_user(user)

    return user


async def get_optional_current_user(
    token: str | None = Depends(oauth2_scheme_optional),
    api_token: str | None = Depends(api_token_scheme),
) -> "User | None":
    try:
        return await get_current_user(token, api_token) if token or api_token else None
    except HTTPException:
        return None


async def get_current_workspace(
    current_user=Depends(get_current_user),
) -> "Workspace | None":
    workspace = context.get_workspace()
    workspace_user = context.get_workspace_user()

    if workspace and workspace_user:
        return workspace

    request = context.get_request()
    workspace_name = request.path_params.get("workspace", None) if request else None

    if not workspace_name:
        return None

    db_reg = get_service(Registry)
    WorkspaceUser = cast(type["WorkspaceUser"], db_reg.get_model("WorkspaceUser"))
    workspace_user = (
        await WorkspaceUser.query.select_related("workspace")
        .filter(user=current_user, workspace__slug=workspace_name)
        .first()
    )

    if not workspace_user or not workspace_user.workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucun workspace trouvé",
        )

    # The join above already carries the row, whole: reading it back by id was a
    # second query on the tenant, once per request of every session.
    workspace = workspace_user.workspace
    context.set_workspace(workspace)
    context.set_workspace_user(workspace_user)

    return workspace


def find_workspace_user_model() -> "type[WorkspaceUser] | None":
    """The concrete workspace-user model of the app (e.g. HouseholdUser) is not
    necessarily registered under the generic 'WorkspaceUser' name — resolve it
    by base class."""
    from fastedgy.models.workspace_user import BaseWorkspaceUser

    db_reg = get_service(Registry)

    for model in db_reg.models.values():
        if (
            isinstance(model, type)
            and issubclass(model, BaseWorkspaceUser)
            and not getattr(model, "__is_proxy_model__", False)
            and not model.meta.abstract
        ):
            return cast(type["WorkspaceUser"], model)

    return None


async def get_workspace_shared_record(current_user=Depends(get_current_user)):
    """Enter the workspace-shareable context requested by the shared-record
    header — ``X-Workspace-Shared-Record: <key>:<id>`` by default, renameable
    per app through the ``workspace_shared_record_header`` setting (no-op
    without the header).

    Loads the root record, its membership row for the current user, delegates
    the business decision to the root's ``workspace_shareable_authorize`` hook
    (refusal → 404, the record's existence is not revealed), then runs the rest
    of the request as the record's workspace (run-as) with the confinement
    filters armed through the ``workspace_shared_record`` context param.
    """
    from fastedgy.orm.workspace_shareable import (
        WORKSPACE_SHARED_RECORD_HEADER,
        WorkspaceShareableRegistry,
    )

    settings = get_service(BaseSettings)
    header_name = getattr(settings, "workspace_shared_record_header", None) or WORKSPACE_SHARED_RECORD_HEADER

    request = context.get_request()
    header = request.headers.get(header_name) if request else None

    if not header:
        yield None
        return

    key, sep, raw_id = header.partition(":")
    key = key.strip()
    raw_id = raw_id.strip()

    if not sep or not key or not raw_id.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {header_name} header",
        )

    registry = get_service(WorkspaceShareableRegistry)
    root = registry.get_root(key)

    if root is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown shared record type '{key}'",
        )

    record_id = int(raw_id)
    record = await root.root_model.global_query.filter(pk=record_id).first()

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared record not found")

    member = None

    if root.member_model is not None:
        member = await root.member_model.global_query.filter(
            **{root.member_record_field: record_id, root.member_user_field: current_user}
        ).first()

    authorize = getattr(root.root_model, "workspace_shareable_authorize", None)
    allowed = await authorize(record, current_user, member) if authorize else member is not None

    if not allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared record not found")

    workspace_field = root.root_model.meta.fields.get("workspace")
    workspace_model = getattr(workspace_field, "target", None)
    workspace_pk = getattr(getattr(record, "workspace", None), "pk", None)

    if isinstance(workspace_model, type) and workspace_pk is not None:
        workspace = await workspace_model.global_query.filter(pk=workspace_pk).first()

        if workspace is not None:
            context.set_workspace(workspace)

            workspace_user = None
            workspace_user_model = find_workspace_user_model()

            if workspace_user_model is not None:
                workspace_user = await workspace_user_model.global_query.filter(
                    user=current_user, workspace=workspace
                ).first()

            context.set_workspace_user(workspace_user)

    with context.params(
        workspace_shared_record=(key, record_id),
        workspace_shared_record_member=member,
        workspace_shared_record_instance=record,
    ):
        yield record


__all__ = [
    "authenticate_user",
    "create_access_token",
    "create_refresh_token",
    "get_current_user",
    "get_current_workspace",
    "get_optional_current_user",
    "get_workspace_shared_record",
    "get_hasher_registry",
    "hash_password",
    "hash_password_async",
    "oauth2_scheme",
    "oauth2_scheme_optional",
    "rehash_password_if_needed",
    "verify_password",
    "verify_password_async",
]
