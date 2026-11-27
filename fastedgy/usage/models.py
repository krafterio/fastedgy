# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime

from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.usage.limits import LimitWindow


class UsageLimitMixin(BaseModel):
    """What a limit of a quota holds, without registering as a model: the
    application declares the concrete one, with the enum of its quotas (`quota`)
    and what the limit belongs to (a plan, a workspace)."""

    class Meta(BaseModel.Meta):
        abstract = True

    window: LimitWindow = fields.ChoiceField(LimitWindow, label=_ts("Window"))

    limit: int = fields.BigIntegerField(label=_ts("Limit"))


class CreditGrantMixin(BaseModel):
    """What a stock of credits offered on top of the limits holds, without
    registering as a model: the application declares the concrete one, with the
    enum of its quotas (`quota`) and who the stock is offered to."""

    class Meta(BaseModel.Meta):
        abstract = True

    credits: int = fields.BigIntegerField(label=_ts("Credits"))

    used: int = fields.BigIntegerField(default=0, read_only=True, label=_ts("Used credits"))

    expires_at: datetime | None = fields.DateTimeField(
        null=True,
        label=_ts("Expires at"),
        description=_ts("Empty: the stock does not expire, it lasts until it is spent."),
    )


__all__ = [
    "CreditGrantMixin",
    "UsageLimitMixin",
]
