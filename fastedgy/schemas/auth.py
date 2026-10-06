# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Annotated

from pydantic_core import PydanticCustomError

from fastedgy.schemas import AfterValidator, BaseModel, EmailStr


def _long_enough(password: str) -> str:
    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service, has_service
    from fastedgy.i18n import _t

    minimum = get_service(BaseSettings).auth_password_min_length if has_service(BaseSettings) else 0

    if len(password) < minimum:
        message = _t("Password must be at least {length} characters", length=minimum)

        raise PydanticCustomError("password_too_short", "{message}", {"message": message, "min_length": minimum})

    return password


NewPassword = Annotated[str, AfterValidator(_long_enough)]


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenRefresh(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRegisterRequest(BaseModel):
    name: str | None = None
    email: EmailStr
    password: NewPassword


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordValidateRequest(BaseModel):
    token: str


class ForgotPasswordValidate(BaseModel):
    email: str
    valid: bool


class ResetPasswordRequest(BaseModel):
    token: str
    password: NewPassword


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: NewPassword


class PasswordChanged(Token):
    message: str


__all__ = [
    "ChangePasswordRequest",
    "ForgotPasswordRequest",
    "NewPassword",
    "PasswordChanged",
    "ResetPasswordRequest",
    "Token",
    "TokenRefresh",
    "UserLogin",
    "UserRegisterRequest",
]
