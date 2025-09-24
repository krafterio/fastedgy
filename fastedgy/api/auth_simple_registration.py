# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, cast
from fastapi import APIRouter, Body, HTTPException, status
from fastedgy import context
from fastedgy.orm import Registry
from fastedgy.depends.security import hash_password
from fastedgy.dependencies import Inject
from fastedgy.schemas.auth import UserRegisterRequest
from fastedgy.schemas.base import SimpleMessage

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register_user(
    user_data: UserRegisterRequest = Body(),
    registry: Registry = Inject(Registry),
) -> SimpleMessage:
    user_model = cast(type["User"], registry.get_model("User"))

    existing_user = await user_model.query.filter(email=user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    hashed_password = hash_password(user_data.password)
    user = user_model(
        name=user_data.name,
        email=user_data.email,
        password=hashed_password,
    )
    await user.save()

    context.set_user(user)

    return SimpleMessage(message="User registered successfully")


__all__ = [
    "router",
]
