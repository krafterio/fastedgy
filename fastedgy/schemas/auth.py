# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pydantic import BaseModel, EmailStr

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


class UserRegister(BaseModel):
    name: str | None = None
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


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
    "UserRegister",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
    "ChangePasswordRequest",
]
