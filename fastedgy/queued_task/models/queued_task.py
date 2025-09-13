# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, Optional, TYPE_CHECKING

from datetime import datetime

from enum import Enum

from fastedgy.orm import Model, fields
from fastedgy.models.base import BaseModel

if TYPE_CHECKING:
    from fastedgy.models.queued_task import QueuedTask


class QueuedTaskState(str, Enum):
    enqueued = "enqueued"
    waiting = "waiting"
    doing = "doing"
    stopped = "stopped"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class QueuedTaskMixin(BaseModel):
    """
    Mixin for queues task functionality.
    This provides all the queues task logic without registering as a model.
    """

    class Meta: # type: ignore
        abstract = True
        label = "Tâche en file d'attente"
        label_plural = "Tâches en file d'attente"
        indexes = [
            fields.Index(fields=["state", "date_enqueued"], name="idx_queued_tasks_state_date"),
            fields.Index(fields=["parent_task"], name="idx_queued_tasks_parent"),
            fields.Index(fields=["parent_task", "state"], name="idx_queued_tasks_parent_state"),
            fields.Index(fields=["state"], name="idx_queued_tasks_state"),
            fields.Index(fields=["date_enqueued"], name="idx_queued_tasks_date_enqueued"),
            fields.Index(fields=["date_ended"], name="idx_queued_tasks_date_ended"),
        ]

    name: Optional[str] = fields.CharField(max_length=255, null=True, label="Nom de la tâche") # type: ignore
    module_name: Optional[str] = fields.CharField(max_length=255, null=True, label="Nom du module") # type: ignore
    function_name: Optional[str] = fields.CharField(max_length=255, null=True, label="Nom de la fonction") # type: ignore
    serialized_function: Optional[bytes] = fields.BinaryField(null=True, label="Fonction sérialisée") # type: ignore
    state: QueuedTaskState = fields.ChoiceField(choices=QueuedTaskState, default=QueuedTaskState.enqueued, label="État") # type: ignore

    args: list = fields.JSONField(default=list, label="Arguments positionnels") # type: ignore
    kwargs: dict = fields.JSONField(default=dict, label="Arguments nommés") # type: ignore
    context: dict = fields.JSONField(default=dict, label="Contexte de la tâche") # type: ignore

    parent_task: Optional["QueuedTask"] = fields.ForeignKey("QueuedTask", on_delete="CASCADE", null=True, label="Task parent") # type: ignore

    exception_name: Optional[str] = fields.CharField(max_length=255, null=True, label="Nom de l'exception") # type: ignore
    exception_message: Optional[str] = fields.TextField(null=True, label="Message d'exception") # type: ignore
    exception_info: Optional[str] = fields.TextField(null=True, label="Informations d'exception") # type: ignore

    execution_time: float = fields.FloatField(default=0.0, label="Temps d'exécution (secondes)") # type: ignore

    date_enqueued: Optional[datetime] = fields.DateTimeField(null=True, label="Date de mise en queue") # type: ignore
    date_started: Optional[datetime] = fields.DateTimeField(null=True, label="Date de démarrage") # type: ignore
    date_stopped: Optional[datetime] = fields.DateTimeField(null=True, label="Date d'arrêt") # type: ignore
    date_ended: Optional[datetime] = fields.DateTimeField(null=True, label="Date de fin") # type: ignore
    date_done: Optional[datetime] = fields.DateTimeField(null=True, label="Date de succès") # type: ignore
    date_cancelled: Optional[datetime] = fields.DateTimeField(null=True, label="Date d'annulation") # type: ignore
    date_failed: Optional[datetime] = fields.DateTimeField(null=True, label="Date d'échec") # type: ignore

    async def save(
        self: Model,
        force_insert: bool = False,
        values: dict[str, Any] | set[str] | None = None,
        force_save: bool | None = None,
    ) -> Model:
        """Override save to auto-generate name and compute dates"""
        if not self.name:
            if self.module_name and self.function_name:
                self.name = f"{self.module_name}.{self.function_name}"
            else:
                self.name = "local_function"
        if not self.date_enqueued and self.state == QueuedTaskState.enqueued:
            self.date_enqueued = datetime.now()

        self._compute_date_ended()
        self._compute_execution_time()

        return super().save(force_insert, values, force_save) # type: ignore

    def _compute_date_ended(self):
        """Automatically compute end date based on the last significant date"""
        if hasattr(self, 'date_done') and self.date_done:
            self.date_ended = self.date_done
        elif hasattr(self, 'date_cancelled') and self.date_cancelled:
            self.date_ended = self.date_cancelled
        elif hasattr(self, 'date_failed') and self.date_failed:
            self.date_ended = self.date_failed
        elif hasattr(self, 'date_stopped') and self.date_stopped:
            self.date_ended = self.date_stopped
        else:
            self.date_ended = None

    def _compute_execution_time(self):
        """Automatically compute execution time"""
        if hasattr(self, 'date_started') and self.date_started and hasattr(self, 'date_ended') and self.date_ended:
            delta = self.date_ended - self.date_started
            self.execution_time = delta.total_seconds()
        elif hasattr(self, 'execution_time') and self.execution_time is None:
            self.execution_time = 0.0

    def mark_as_doing(self):
        """Mark task as running"""
        self.state = QueuedTaskState.doing
        self.date_started = datetime.now()
        self.date_stopped = None
        self.date_done = None
        self.date_cancelled = None
        self.date_failed = None
        self.date_ended = None
        self.exception_name = None
        self.exception_message = None
        self.exception_info = None

    def mark_as_done(self):
        """Mark task as successfully completed"""
        self.state = QueuedTaskState.done
        self.date_done = datetime.now()

    def mark_as_failed(self, exception_name: str | None = None, exception_message: str | None = None, exception_info: str | None = None):
        """Mark task as failed"""
        self.state = QueuedTaskState.failed
        self.date_failed = datetime.now()
        if exception_name:
            self.exception_name = exception_name
        if exception_message:
            self.exception_message = exception_message
        if exception_info:
            self.exception_info = exception_info

    def mark_as_stopped(self):
        """Mark task as stopped"""
        self.state = QueuedTaskState.stopped
        self.date_stopped = datetime.now()

    def mark_as_cancelled(self):
        """Mark task as cancelled"""
        self.state = QueuedTaskState.cancelled
        self.date_cancelled = datetime.now()

    def mark_as_waiting(self):
        """Mark task as waiting"""
        self.state = QueuedTaskState.waiting

    def restart(self):
        """Reset task to queue by resetting all state fields"""
        self.state = QueuedTaskState.enqueued
        self.date_enqueued = datetime.now()
        self._reset_execution_fields()

    def _reset_execution_fields(self):
        """Reset all execution-related fields"""
        self.date_started = None
        self.date_stopped = None
        self.date_ended = None
        self.date_done = None
        self.date_cancelled = None
        self.date_failed = None
        self.execution_time = 0.0
        self.exception_name = None
        self.exception_message = None
        self.exception_info = None

    @property
    def is_finished(self) -> bool:
        """Check if task is in a final state"""
        return hasattr(self, 'state') and self.state in [QueuedTaskState.done, QueuedTaskState.failed, QueuedTaskState.cancelled]

    @property
    def is_active(self) -> bool:
        """Check if task is active (running or waiting)"""
        return hasattr(self, 'state') and self.state in [QueuedTaskState.enqueued, QueuedTaskState.waiting, QueuedTaskState.doing]

    @property
    def can_be_restarted(self) -> bool:
        """Check if task can be restarted"""
        return hasattr(self, 'state') and self.state in [QueuedTaskState.stopped, QueuedTaskState.failed]

    @property
    def can_be_cancelled(self) -> bool:
        """Check if task can be cancelled"""
        return hasattr(self, 'state') and self.state in [QueuedTaskState.enqueued, QueuedTaskState.waiting, QueuedTaskState.doing]
