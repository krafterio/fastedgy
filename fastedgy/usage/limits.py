# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastedgy import context
from fastedgy.dependencies import get_service
from fastedgy.i18n import _t, _ts
from fastedgy.orm.access_guard import AccessDeniedError
from fastedgy.orm.fields import ChoiceEnum

ROLLING = timedelta(hours=5)
WEEK = timedelta(days=7)


class LimitWindow(ChoiceEnum):
    """What a limit counts over: the five hours before now, the day and the month
    of the calendar in the timezone of the request, or the week of the workspace,
    which starts every seven days from the anchor of its reach."""

    rolling_5h = _ts("Rolling 5 hours")
    day = _ts("Day")
    week = _ts("Subscription week")
    month = _ts("Calendar month")


WINDOW_ORDER = (LimitWindow.rolling_5h, LimitWindow.day, LimitWindow.week, LimitWindow.month)


@dataclass(frozen=True)
class Reach:
    """What the quotas of a workspace count, as the application answers it
    (`UsageSource.reach`). An application subclasses it to carry what its limits
    need (a plan, a subscription).

    [anchor] starts the weeks of the limits; [shared] names the workspaces whose
    usages count together with this one's (a list of ids or a select of them),
    None for this workspace alone; [scope] is how a usage screen names that reach.
    """

    anchor: datetime
    workspace_id: int
    shared: Any = None
    scope: str = "workspace"

    def workspaces(self) -> Any:
        return [self.workspace_id] if self.shared is None else self.shared


@dataclass(frozen=True)
class UsageLimit:
    """One limit of a workspace: at most [limit] of [quota] over [window]."""

    quota: ChoiceEnum
    window: LimitWindow
    limit: int


@dataclass(frozen=True)
class UsageEntry:
    """What a workspace used of a quota over a window, against its limit if it has one."""

    quota: ChoiceEnum
    window: LimitWindow
    used: int
    limit: int | None
    reset_at: datetime | None


class QuotaExceeded(AccessDeniedError):
    """A usage refused because a limit of its quota is reached, until [reset_at]."""

    def __init__(self, quota: ChoiceEnum, window: LimitWindow, limit: int, reset_at: datetime, message: str):
        super().__init__(message)
        self.quota = quota
        self.window = window
        self.limit = limit
        self.reset_at = reset_at

    @property
    def message(self) -> str:
        return str(self.detail)


class UsageCounter:
    """How the usage of a quota is counted: what it consumed since each of [starts],
    for the workspaces of a reach. An application gives one to each quota it limits
    (`UsageQuotas.count`), over wherever that usage is already written."""

    async def used(self, quota: ChoiceEnum, reach: Reach, starts: list[datetime]) -> list[int]:
        raise NotImplementedError

    async def back_under_limit(
        self, quota: ChoiceEnum, reach: Reach, start: datetime, now: datetime, excess: int
    ) -> datetime:
        """When a rolling window that counts [excess] too much since [start] is back
        under its limit: once the whole window has passed, unless the counter knows
        when enough of it falls out."""
        return now + ROLLING


class UsageSource:
    """What the application answers about the quotas of a workspace: what they
    count ([reach]), their limits, and what a refusal says. Registered in place of
    this one, which limits nothing."""

    async def reach(self, workspace: Any) -> Reach | None:
        """What the quotas of the workspace count. None: nothing is limited."""
        created_at = getattr(workspace, "created_at", None)

        return Reach(anchor=created_at or datetime(2000, 1, 1, tzinfo=UTC), workspace_id=workspace.id)

    async def limits(self, reach: Reach) -> list[UsageLimit]:
        """The limits of the workspace a [reach] is of, whatever their quota."""
        return []

    def refusal(self, quota: ChoiceEnum, window: LimitWindow, limit: int, reset_at: datetime) -> str:
        """What a usage refused says to who asked for it."""
        return str(_t("The limit of this usage is reached. It opens again later."))


class UsageQuotas:
    """The quotas the application limits, each with how its usage is counted."""

    def __init__(self) -> None:
        self._counters: dict[str, UsageCounter] = {}

    def count(self, quota: ChoiceEnum, counter: UsageCounter) -> None:
        self._counters[quota.name] = counter

    def counter_of(self, quota: ChoiceEnum) -> UsageCounter:
        counter = self._counters.get(quota.name)

        if counter is None:
            raise LookupError(f"No counter is declared for the quota {quota.name!r} (UsageQuotas.count)")

        return counter

    def counts(self, quota: ChoiceEnum) -> bool:
        return quota.name in self._counters


def usage_source() -> UsageSource:
    return get_service(UsageSource)


def usage_quotas() -> UsageQuotas:
    return get_service(UsageQuotas)


async def reach_of(workspace: Any) -> Reach | None:
    return await usage_source().reach(workspace)


def window_bounds(window: LimitWindow, reach: Reach, now: datetime) -> tuple[datetime, datetime | None]:
    """When a window that holds [now] starts and ends: a rolling one has no end."""
    if window == LimitWindow.rolling_5h:
        return now - ROLLING, None

    if window == LimitWindow.week:
        start = reach.anchor + WEEK * ((now - reach.anchor) // WEEK)

        return start, start + WEEK

    midnight = now.astimezone(context.get_timezone()).replace(hour=0, minute=0, second=0, microsecond=0)

    if window == LimitWindow.day:
        return midnight, (midnight + timedelta(hours=36)).replace(hour=0)

    start = midnight.replace(day=1)

    return start, (start + timedelta(days=32)).replace(day=1)


async def quota_limits(reach: Reach, quota: ChoiceEnum) -> list[UsageLimit]:
    """The limits of one quota for a reach, the shortest window first."""
    limits = [limit for limit in await usage_source().limits(reach) if limit.quota == quota]

    return sorted(limits, key=lambda limit: WINDOW_ORDER.index(limit.window))


async def used(quota: ChoiceEnum, reach: Reach, starts: list[datetime]) -> list[int]:
    """What a reach used of a quota since each of [starts]."""
    return await usage_quotas().counter_of(quota).used(quota, reach, starts)


async def check_limits(quota: ChoiceEnum, *, pending: int = 0, workspace: Any = None) -> None:
    """Refuse a usage of a quota that reaches one of its limits, [pending] being
    what it is about to add: the workspace of the context, or the one given."""
    workspace = workspace if workspace is not None else context.get_workspace()

    if workspace is None:
        return

    reach = await reach_of(workspace)

    if reach is None:
        return

    limits = await quota_limits(reach, quota)

    if not limits:
        return

    now = datetime.now(UTC)
    bounds = [window_bounds(limit.window, reach, now) for limit in limits]
    consumed = await used(quota, reach, [start for start, _ in bounds])

    for limit, (start, end), count in zip(limits, bounds, consumed, strict=True):
        if count + pending < limit.limit:
            continue

        reset_at = end or await usage_quotas().counter_of(quota).back_under_limit(
            quota, reach, start, now, count + pending - limit.limit + 1
        )

        raise QuotaExceeded(
            quota,
            limit.window,
            limit.limit,
            reset_at,
            usage_source().refusal(quota, limit.window, limit.limit, reset_at),
        )


async def quota_entries(reach: Reach, quota: ChoiceEnum, *, shown: tuple[LimitWindow, ...] = ()) -> list[UsageEntry]:
    """What a reach used of a quota, over each window it is limited on and over
    those of [shown] it is not, the shortest window first."""
    limits = await quota_limits(reach, quota)
    windows = [
        *(limit.window for limit in limits),
        *(window for window in shown if all(window != limit.window for limit in limits)),
    ]

    if not windows:
        return []

    now = datetime.now(UTC)
    bounds = [window_bounds(window, reach, now) for window in windows]
    consumed = await used(quota, reach, [start for start, _ in bounds])
    limit_of = {limit.window: limit.limit for limit in limits}
    entries: list[UsageEntry] = []

    for window, (start, end), count in zip(windows, bounds, consumed, strict=True):
        limit = limit_of.get(window)
        reset_at = end

        if end is None and limit is not None and count >= limit:
            reset_at = (
                await usage_quotas().counter_of(quota).back_under_limit(quota, reach, start, now, count - limit + 1)
            )

        entries.append(UsageEntry(quota, window, count, limit, reset_at))

    return sorted(entries, key=lambda entry: WINDOW_ORDER.index(entry.window))


__all__ = [
    "ROLLING",
    "WEEK",
    "WINDOW_ORDER",
    "LimitWindow",
    "QuotaExceeded",
    "Reach",
    "UsageCounter",
    "UsageEntry",
    "UsageLimit",
    "UsageQuotas",
    "UsageSource",
    "check_limits",
    "quota_entries",
    "quota_limits",
    "reach_of",
    "usage_quotas",
    "usage_source",
    "used",
    "window_bounds",
]
