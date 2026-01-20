# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel


class BaseUser(BaseModel):
    class Meta(BaseModel.Meta):  # type: ignore
        abstract = True
        label = "Utilisateur"
        label_plural = "Utilisateurs"
        model_name: str | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        meta = getattr(cls, "Meta", None)
        if not meta or getattr(meta, "abstract", False):
            return

        if BaseUser.Meta.model_name is None:
            BaseUser.Meta.model_name = cls.__name__
            return

        if BaseUser.Meta.model_name == cls.__name__:
            return

        raise RuntimeError(
            f"Multiple user models detected: "
            f"{BaseUser.Meta.model_name} and {cls.__name__}"
        )

    email: str | None = fields.EmailField(unique=True, label="Email")  # type: ignore
    name: str | None = fields.CharField(max_length=255, null=True, label="Nom")  # type: ignore
    password: str | None = fields.PasswordField(exclude=True, label="Mot de passe")  # type: ignore
    initials: str | None = fields.ComputedField(getter="get_initials", label="Initials")  # type: ignore
    reset_pwd_token: str | None = fields.CharField(
        max_length=255,
        null=True,
        exclude=True,
        label="Token de réinitialisation de mot de passe",
    )  # type: ignore
    reset_pwd_expires_at: datetime | None = fields.DateTimeField(
        null=True,
        exclude=True,
        label="Date d'expiration du token de réinitialisation de mot de passe",
    )  # type: ignore

    @classmethod
    def get_initials(cls, field, instance, owner=None) -> str:
        if instance.name:
            words = instance.name.split()
            initials = "".join([word[:2].upper() for word in words if word])

            return initials[:6]

        return instance.email[0].upper() if instance.email else ""


__all__ = [
    "BaseUser",
]
