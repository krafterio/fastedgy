# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n import _ts

from datetime import datetime

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel


class BaseUser(BaseModel):
    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("User")
        label_plural = _ts("Users")
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

        raise RuntimeError(f"Multiple user models detected: {BaseUser.Meta.model_name} and {cls.__name__}")

    email: str | None = fields.EmailField(unique=True, label=_ts("Email"))

    name: str | None = fields.CharField(max_length=255, null=True, label=_ts("Name"))

    password: str | None = fields.PasswordField(exclude=True, null=True, label=_ts("Password"))

    initials: str | None = fields.ComputedField(getter="get_initials", label=_ts("Initials"))

    reset_pwd_token: str | None = fields.CharField(
        max_length=255,
        null=True,
        exclude=True,
        label=_ts("Password reset token"),
    )

    reset_pwd_expires_at: datetime | None = fields.DateTimeField(
        null=True,
        exclude=True,
        label=_ts("Password reset token expiration"),
    )

    @classmethod
    def get_initials(cls, field, instance, owner=None) -> str:
        if instance.name:
            words = instance.name.split()
            initials = "".join([word[:2].upper() for word in words if word])

            return initials[:6]

        return instance.email[0].upper() if instance.email else ""

    def set_password(self, raw_password: str) -> None:
        from fastedgy.depends.security import hash_password

        self.password = hash_password(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        from fastedgy.depends.security import verify_password

        return verify_password(self.password, raw_password)


__all__ = [
    "BaseUser",
]
