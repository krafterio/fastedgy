# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Union
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastedgy.config import get_settings
from fastedgy import context
from passlib.context import CryptContext

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, verify_password: str) -> bool:
    if not password or not verify_password:
        return False

    return pwd_context.verify(verify_password, password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    settings = get_settings()
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.auth_access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm)
    return encoded_jwt


def create_refresh_token(data: dict):
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.auth_refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm)
    return encoded_jwt


async def authenticate_user(email: str, password: str):
    settings = get_settings()
    db_reg = settings.db_registry
    user = await db_reg.get_model('User').query.filter(email=email).first() # type: ignore

    if not user or not verify_password(user.password, password):
        return False

    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> "User":
    user = context.get_user()
    if user:
        return user

    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])
        email: str = str(payload.get("sub"))
        token_type: str = str(payload.get("type"))

        if email is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    db_reg = settings.db_registry
    user = await db_reg.get_model('User').query.filter(email=email).first() # type: ignore

    if user is None:
        raise credentials_exception

    context.set_user(user)

    return user


async def get_current_workspace(current_user = Depends(get_current_user)) -> Union["Workspace", None]:
    workspace = context.get_workspace()
    workspace_user = context.get_workspace_user()

    if workspace and workspace_user:
        return workspace

    request = context.get_request()
    workspace_name = request.path_params.get("workspace", None) # type: ignore

    if not workspace_name:
        return None

    settings = get_settings()
    db_reg = settings.db_registry
    workspace_user = await db_reg.get_model('WorkspaceUser').query.select_related('workspace').filter(user=current_user, workspace__slug=workspace_name).first() # type: ignore

    if not workspace_user or not workspace_user.workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucun workspace trouvé",
        )

    workspace = await db_reg.get_model('Workspace').query.get(id=workspace_user.workspace.id) # type: ignore
    context.set_workspace(workspace)
    context.set_workspace_user(workspace_user)

    return workspace
