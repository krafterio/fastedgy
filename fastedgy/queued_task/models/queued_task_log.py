# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING

from datetime import datetime

from fastedgy.orm import fields
from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


class QueuedTaskLogType(fields.ChoiceEnum):
    critical = _ts("Critical")
    error = _ts("Error")
    warning = _ts("Warning")
    info = _ts("Info")
    debug = _ts("Debug")


class QueuedTaskLogMixin(BaseModel):
    """
    Mixin for queues task log functionality.
    This provides all the queues task log logic without registering as a model.
    """

    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("Queued task log")
        label_plural = _ts("Queued task logs")
        indexes = [
            fields.Index(fields=["task", "logged_at"], name="idx_queued_task_logs_task_date"),
            fields.Index(fields=["log_type", "logged_at"], name="idx_queued_task_logs_type_date"),
            fields.Index(fields=["logged_at"], name="idx_queued_task_logs_date"),
        ]

    task: "QueuedTask" = fields.ForeignKey("QueuedTask", on_delete="CASCADE", label=_ts("Task"), related_name="logs")

    log_type: QueuedTaskLogType = fields.ChoiceField(choices=QueuedTaskLogType, label=_ts("Log type"))

    logged_at: datetime | None = fields.DateTimeField(
        default_factory=datetime.now,
        read_only=True,
        auto_now_add=True,
        label=_ts("Timestamp"),
    )

    name: str | None = fields.CharField(max_length=255, null=True, label=_ts("Name"))

    message: str | None = fields.TextField(null=True, label=_ts("Message"))

    info: str | None = fields.TextField(null=True, label=_ts("Information"))
