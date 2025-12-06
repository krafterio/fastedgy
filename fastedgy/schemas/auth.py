# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.schemas import BaseModel, EmailStr


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
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordValidateRequest(BaseModel):
    token: str


class ForgotPasswordValidate(BaseModel):
    email: str
    valid: bool


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


__all__ = [
    "Token",
    "TokenRefresh",
    "UserLogin",
    "UserRegisterRequest",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
    "ChangePasswordRequest",
]
