# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Type, cast
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastedgy.config import get_settings
from fastedgy.depends.security import authenticate_user, create_access_token, create_refresh_token, get_current_user, hash_password
from fastedgy.schemas.auth import ChangePasswordRequest, ResetPasswordRequest, Token, TokenRefresh
from fastedgy.schemas.base import Message
from jose import jwt, JWTError
from datetime import datetime, timedelta


if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User


router = APIRouter(prefix="/auth", tags=["auth"])
public_router = APIRouter(prefix="/auth", tags=["auth"])


@public_router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    user = await authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    access_token_expires = timedelta(minutes=settings.auth_access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": user.email})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )

@public_router.post("/refresh")
async def refresh_access_token(token_data: TokenRefresh) -> Token:
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token_data.refresh_token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])
        email: str = str(payload.get("sub"))
        token_type: str = str(payload.get("type"))
        if email is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await User.query.filter(email=email).first() # type: ignore
    if user is None:
        raise credentials_exception

    access_token_expires = timedelta(minutes=settings.auth_access_token_expire_minutes)
    new_access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    new_refresh_token = create_refresh_token(data={"sub": user.email})

    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@public_router.post("/password/reset")
async def password_reset(data: ResetPasswordRequest) -> Message:
    from fastedgy.models.user import BaseUser as User
    settings = get_settings()
    db_reg = settings.db_registry
    User = cast(Type["User"], db_reg.get_model('User'))

    user = await User.query.filter( # type: ignore
        User.columns.reset_pwd_token == data.token,
        User.columns.reset_pwd_expires_at >= datetime.now()
    ).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token invalid or expired")

    user.password = hash_password(data.password)
    user.reset_pwd_token = None
    user.reset_pwd_expires_at = None
    await user.save()

    return Message(message="Password updated")


@router.post("/password/change")
async def change_password(
    data: ChangePasswordRequest,
    current_user: "User" = Depends(get_current_user)
) -> Message:
    from fastedgy.models.user import BaseUser as User
    settings = get_settings()
    db_reg = settings.db_registry
    User = cast(Type["User"], db_reg.get_model('User'))

    if not current_user.verify_password(data.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    current_user.password = hash_password(data.new_password)
    await current_user.save()

    return Message(message="Password changed successfully")


__all__ = [
    "router",
    "public_router",
]
