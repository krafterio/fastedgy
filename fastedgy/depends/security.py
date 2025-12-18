# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Union, cast
from fastedgy.dependencies import get_service
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastedgy import context
from fastedgy.config import BaseSettings
from fastedgy.orm import Registry
from passlib.context import CryptContext


if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace
    from fastedgy.models.workspace_user import BaseWorkspaceUser as WorkspaceUser


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token", auto_error=False
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, verify_password: str) -> bool:
    if not password or not verify_password:
        return False

    return pwd_context.verify(verify_password, password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    settings = get_service(BaseSettings)
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.auth_access_token_expire_minutes
        )
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(
        to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm
    )
    return encoded_jwt


def create_refresh_token(data: dict):
    settings = get_service(BaseSettings)
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.auth_refresh_token_expire_days
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm
    )
    return encoded_jwt


async def authenticate_user(email: str, password: str):
    db_reg = get_service(Registry)
    User = cast(type["User"], db_reg.get_model("User"))

    if hasattr(User, "username") or "username" in User.model_fields:
        user = await User.query.filter(
            (User.columns.email == email) | (User.columns.username == email)
        ).first()
    else:
        user = await User.query.filter(email=email).first()

    if not user or not verify_password(user.password, password):
        return False

    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> "User":
    user = context.get_user()
    if user:
        return user

    settings = get_service(BaseSettings)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.auth_secret_key, algorithms=[settings.auth_algorithm]
        )
        email: str = str(payload.get("sub"))
        token_type: str = str(payload.get("type"))

        if email is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    db_reg = get_service(Registry)
    User = cast(type["User"], db_reg.get_model("User"))

    if hasattr(User, "username") or "username" in User.model_fields:
        user = await User.query.filter(
            (User.columns.email == email) | (User.columns.username == email)
        ).first()
    else:
        user = await User.query.filter(email=email).first()

    if user is None:
        raise credentials_exception

    context.set_user(user)

    return user


async def get_optional_current_user(
    token: str | None = Depends(oauth2_scheme_optional),
) -> Optional["User"]:
    try:
        return await get_current_user(token) if token else None
    except HTTPException:
        return None


async def get_current_workspace(
    current_user=Depends(get_current_user),
) -> Union["Workspace", None]:
    workspace = context.get_workspace()
    workspace_user = context.get_workspace_user()

    if workspace and workspace_user:
        return workspace

    request = context.get_request()
    workspace_name = request.path_params.get("workspace", None)  # type: ignore

    if not workspace_name:
        return None

    db_reg = get_service(Registry)
    Workspace = cast(type["Workspace"], db_reg.get_model("Workspace"))
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

    workspace = await Workspace.query.get(id=workspace_user.workspace.id)  # type: ignore
    context.set_workspace(workspace)
    context.set_workspace_user(workspace_user)

    return workspace


__all__ = [
    "oauth2_scheme",
    "oauth2_scheme_optional",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "authenticate_user",
    "get_current_user",
    "get_optional_current_user",
    "get_current_workspace",
]
