# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy import fields

from fastedgy.models.base import BaseModel


class BaseUser(BaseModel):
    class Meta:  # type: ignore
        tablename = "users"
        label = "Utilisateur"
        label_plural = "Utilisateurs"

    email: str | None = fields.EmailField(unique=True, label="Email")  # type: ignore
    name: str | None = fields.CharField(max_length=255, null=True, label="Nom")  # type: ignore
    password: str | None = fields.PasswordField(exclude=True, label="Mot de passe")  # type: ignore
    initials: str | None = fields.ComputedField(getter="get_initials", label="Initials")  # type: ignore

    @classmethod
    def get_initials(cls, field, instance, owner=None) -> str:
        if instance.name:
            words = instance.name.split()
            initials = "".join([word[:2].upper() for word in words if word])

            return initials[:6]

        return instance.email[0].upper() if instance.email else ""
