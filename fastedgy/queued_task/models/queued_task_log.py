# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Optional

from datetime import datetime

from enum import Enum

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel

if TYPE_CHECKING:
    from fastedgy.models.queued_task import QueuedTask


class QueuedTaskLogType(str, Enum):
    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"


class QueuedTaskLogMixin(BaseModel):
    """
    Mixin for queues task log functionality.
    This provides all the queues task log logic without registering as a model.
    """

    class Meta:
        abstract = True
        label = "Log Task Queue"
        label_plural = "Logs Task Queue"
        indexes = [
            fields.Index(fields=["task", "logged_at"], name="idx_queued_task_logs_task_date"),
            fields.Index(fields=["log_type", "logged_at"], name="idx_queued_task_logs_type_date"),
            fields.Index(fields=["logged_at"], name="idx_queued_task_logs_date"),
        ]

    task: "QueuedTask" = fields.ForeignKey("QueuedTask", on_delete="CASCADE", label="Tâche", related_name="logs")
    log_type: QueuedTaskLogType = fields.ChoiceField(choices=QueuedTaskLogType, label="Type de log")
    logged_at: datetime | None = fields.DateTimeField(default_factory=datetime.now, read_only=True, auto_now_add=True, label="Horodatage")  # type: ignore
    name: Optional[str] = fields.CharField(max_length=255, null=True, label="Nom")
    message: Optional[str] = fields.TextField(null=True, label="Message")
    info: Optional[str] = fields.TextField(null=True, label="Informations")
