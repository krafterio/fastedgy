# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n import _ts

import re

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

    initials: str | None = fields.ComputedField(
        getter="get_initials", exclude=False, read_only=True, label=_ts("Initials")
    )

    display_name: str | None = fields.ComputedField(
        getter="get_display_name", exclude=False, read_only=True, label=_ts("Display name")
    )

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
    def get_display_name(cls, field, instance, owner=None) -> str:
        """What names the user: their name, or their email until they set one."""
        return instance.name or instance.email or ""

    @classmethod
    def get_initials(cls, field, instance, owner=None) -> str:
        """Initials of the name, or of the email's local part when there is none.

        A single letter would collide for every colleague sharing a first
        initial, so the email is read the way a name is: `jean.dupont@` gives
        `JD`, `francois@` gives `FR`.
        """
        if instance.name:
            words = instance.name.split()
            initials = "".join([word[:2].upper() for word in words if word])

            return initials[:6]

        local = (instance.email or "").split("@")[0]
        words = [word for word in re.split(r"[._\-+]", local) if word]

        if not words:
            return ""

        if len(words) >= 2:
            return f"{words[0][0]}{words[1][0]}".upper()

        return words[0][:2].upper()

    def set_password(self, raw_password: str) -> None:
        from fastedgy.depends.security import hash_password

        self.password = hash_password(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        from fastedgy.depends.security import verify_password

        return verify_password(self.password, raw_password)


__all__ = [
    "BaseUser",
]
