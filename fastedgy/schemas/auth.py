# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pydantic import BaseModel, EmailStr

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenRefresh(BaseModel):
    refresh_token: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRegister(BaseModel):
    name: str | None = None
    email: EmailStr
    password: str


class PasswordForgotRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
