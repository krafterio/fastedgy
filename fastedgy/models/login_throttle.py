# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import UTC, datetime, timedelta

from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel
from fastedgy.orm import Registry, fields
from fastedgy.orm.filter import And, R


class LoginThrottleMixin(BaseModel):
    """The failed sign-ins of one identifier from one address. Past
    ``auth_login_free_attempts`` of them, each new attempt waits a delay that
    doubles up to ``auth_login_max_delay`` seconds; a success clears the row.

    An app opts in by declaring a concrete model on it."""

    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("Sign-in throttle")
        label_plural = _ts("Sign-in throttles")
        unique_together = [("identity", "address")]

    identity: str = fields.CharField(max_length=255, label=_ts("Identifier"))

    address: str = fields.CharField(max_length=64, label=_ts("Address"))

    failures: int = fields.IntegerField(default=0, label=_ts("Failures"))

    last_failure_at: datetime = fields.DateTimeField(label=_ts("Last failure"))


def find_login_throttle_model() -> type[LoginThrottleMixin] | None:
    for model in get_service(Registry).models.values():
        if (
            isinstance(model, type)
            and issubclass(model, LoginThrottleMixin)
            and not getattr(model, "__is_proxy_model__", False)
        ):
            return model

    return None


def _key(identity: str, address: str | None) -> And:
    return And(R("identity", "=", identity.strip().lower()[:255]), R("address", "=", (address or "")[:64]))


def _delay(failures: int, settings: BaseSettings) -> int:
    extra = failures - settings.auth_login_free_attempts

    return 0 if extra < 0 else min(settings.auth_login_max_delay, 2**extra)


async def login_retry_after(identity: str, address: str | None) -> int:
    """Seconds the next attempt of this identifier from this address still has to wait."""
    model = find_login_throttle_model()

    if model is None:
        return 0

    row = await model.global_query.filter(_key(identity, address)).first()

    if row is None:
        return 0

    available = row.last_failure_at + timedelta(seconds=_delay(row.failures, get_service(BaseSettings)))

    return max(0, int((available - datetime.now(UTC)).total_seconds() + 0.999))


async def record_login_failure(identity: str, address: str | None) -> None:
    model = find_login_throttle_model()

    if model is None:
        return

    row = await model.global_query.filter(_key(identity, address)).first()
    now = datetime.now(UTC)

    if row is None:
        row = model(
            identity=identity.strip().lower()[:255], address=(address or "")[:64], failures=0, last_failure_at=now
        )

    row.failures = (getattr(row, "failures", 0) or 0) + 1
    row.last_failure_at = now
    await row.save()


async def clear_login_failures(identity: str, address: str | None) -> None:
    model = find_login_throttle_model()

    if model is not None:
        await model.global_query.filter(_key(identity, address)).delete()


__all__ = [
    "LoginThrottleMixin",
    "clear_login_failures",
    "find_login_throttle_model",
    "login_retry_after",
    "record_login_failure",
]
