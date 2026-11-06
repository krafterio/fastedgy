# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, status

from fastedgy import context
from fastedgy.api.auth import send_email_verification
from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject
from fastedgy.depends.security import email_matches, is_email_verifiable
from fastedgy.i18n import _t
from fastedgy.mail import Mail
from fastedgy.orm import Registry
from fastedgy.schemas.auth import UserRegisterRequest
from fastedgy.schemas.base import SimpleMessage

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register_user(
    background_tasks: BackgroundTasks,
    user_data: UserRegisterRequest = Body(),
    registry: Registry = Inject(Registry),
    mail: Mail = Inject(Mail),
    settings: BaseSettings = Inject(BaseSettings),
) -> SimpleMessage:
    user_model = cast(type["User"], registry.get_model("User"))

    if await user_model.query.filter(email_matches(user_model, user_data.email)).exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_t("Email already registered"))

    user = user_model(
        name=user_data.name,
        email=user_data.email,
        password="",
    )
    user.set_password(user_data.password)
    await user.save()

    context.set_user(user)

    if is_email_verifiable(user_model):
        background_tasks.add_task(send_email_verification, user, mail, settings.base_url_app)

    return SimpleMessage(message=_t("User registered successfully"))


__all__ = [
    "router",
]
