# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, TYPE_CHECKING

from datetime import datetime, timezone

from sqlalchemy import text

from fastedgy.orm import Model, fields
from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


class QueuedTaskState(fields.ChoiceEnum):
    enqueued = _ts("Enqueued")
    waiting = _ts("Waiting")
    doing = _ts("Doing")
    stopped = _ts("Stopped")
    done = _ts("Done")
    failed = _ts("Failed")
    cancelled = _ts("Cancelled")


class QueuedTaskMixin(BaseModel):
    """
    Mixin for queues task functionality.
    This provides all the queues task logic without registering as a model.
    """

    class Meta(BaseModel.Meta):
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
            # Serves the claim's ORDER BY priority DESC, date_enqueued ASC —
            # a mixed-direction sort that a uniform-direction btree cannot
            # provide (every claim would top-1 sort the whole ready backlog).
            # The TextClause carries the per-column direction.
            fields.Index(
                fields=["state", text("priority DESC"), "date_enqueued"],
                name="idx_queued_tasks_state_priority",
            ),
        ]

    name: str | None = fields.CharField(max_length=255, null=True, label="Nom de la tâche")

    module_name: str | None = fields.CharField(max_length=255, null=True, label="Nom du module")

    function_name: str | None = fields.CharField(max_length=255, null=True, label="Nom de la fonction")

    serialized_function: bytes | None = fields.BinaryField(null=True, label="Fonction sérialisée")

    state: QueuedTaskState = fields.ChoiceField(choices=QueuedTaskState, default=QueuedTaskState.enqueued, label="État")

    args: list = fields.JSONField(default=[], label="Arguments positionnels")

    kwargs: dict = fields.JSONField(default={}, label="Arguments nommés")

    context: dict = fields.JSONField(default={}, label="Contexte de la tâche")

    # Execution lane and ordering: the claim picks the highest-priority ready
    # row among the channels that still have a free slot on the claiming
    # container (capacities from QUEUED_TASK_CHANNELS), oldest first within
    # equal priority. Channels are concurrency caps, priority is the global
    # order — see QueuedTaskConfig.channels.
    channel: str = fields.CharField(max_length=64, default="default", label="Channel d'exécution")

    priority: int = fields.IntegerField(default=0, label="Priorité")

    parent_task: "QueuedTask | None" = fields.ForeignKey(
        "QueuedTask", on_delete="CASCADE", null=True, label="Task parent"
    )

    exception_name: str | None = fields.CharField(max_length=255, null=True, label="Nom de l'exception")

    exception_message: str | None = fields.TextField(null=True, label="Message d'exception")

    exception_info: str | None = fields.TextField(null=True, label="Informations d'exception")

    execution_time: float = fields.FloatField(default=0.0, label="Temps d'exécution (secondes)")

    date_enqueued: datetime | None = fields.DateTimeField(null=True, label="Date de mise en queue")

    date_started: datetime | None = fields.DateTimeField(null=True, label="Date de démarrage")

    date_stopped: datetime | None = fields.DateTimeField(null=True, label="Date d'arrêt")

    date_ended: datetime | None = fields.DateTimeField(null=True, label="Date de fin")

    auto_remove: bool = fields.BooleanField(default=False, label="Suppression automatique après succès")

    # Lease ownership: server_name of the worker manager that claimed the
    # task (set by the claim UPDATE, cleared on release/re-enqueue).
    # Cross-checked against queued_task_workers heartbeats, it lets the
    # reaper recover a 'doing' row immediately when its owner dies instead
    # of waiting for the task-timeout criterion — essential with start-first
    # deploys where several containers (= servers) briefly overlap.
    claimed_by: str | None = fields.CharField(max_length=255, null=True, label="Serveur propriétaire")

    # Bounded auto-retry: a failed run is re-enqueued with an exponential
    # delay until retry_count reaches the budget, then fails terminally.
    # max_retries NULL → the QUEUED_TASK_MAX_RETRIES config default applies
    # at failure time. Manual restart/retry resets retry_count (fresh budget).
    retry_count: int = fields.IntegerField(default=0, label="Nombre de tentatives automatiques")

    max_retries: int | None = fields.IntegerField(null=True, label="Nombre maximum de tentatives automatiques")

    date_done: datetime | None = fields.DateTimeField(null=True, label="Date de succès")

    date_cancelled: datetime | None = fields.DateTimeField(null=True, label="Date d'annulation")

    date_failed: datetime | None = fields.DateTimeField(null=True, label="Date d'échec")

    async def save(
        self,
        force_insert: bool = False,
        values: dict[str, Any] | set[str] | None = None,
        force_save: bool | None = None,
    ) -> Model:
        """Override save to auto-generate name and compute dates"""
        if not hasattr(self, "name") or not self.name:
            if (
                hasattr(self, "module_name")
                and self.module_name
                and hasattr(self, "function_name")
                and self.function_name
            ):
                self.name = f"{self.module_name}.{self.function_name}"
            else:
                self.name = "local_function"
        if not hasattr(self, "date_enqueued") or not self.date_enqueued and self.state == QueuedTaskState.enqueued:
            self.date_enqueued = datetime.now(timezone.utc)

        self._compute_date_ended()
        self._compute_execution_time()

        return await super().save(force_insert, values, force_save)

    def _compute_date_ended(self):
        """Automatically compute end date based on the last significant date"""
        if hasattr(self, "date_done") and self.date_done:
            self.date_ended = self.date_done
        elif hasattr(self, "date_cancelled") and self.date_cancelled:
            self.date_ended = self.date_cancelled
        elif hasattr(self, "date_failed") and self.date_failed:
            self.date_ended = self.date_failed
        elif hasattr(self, "date_stopped") and self.date_stopped:
            self.date_ended = self.date_stopped
        else:
            self.date_ended = None

    def _compute_execution_time(self):
        """Automatically compute execution time"""
        if hasattr(self, "date_started") and self.date_started and hasattr(self, "date_ended") and self.date_ended:
            delta = self.date_ended - self.date_started
            self.execution_time = delta.total_seconds()
        elif hasattr(self, "execution_time") and self.execution_time is None:
            self.execution_time = 0.0

    def mark_as_doing(self):
        """Mark task as running"""
        self.state = QueuedTaskState.doing
        self.date_started = datetime.now(timezone.utc)
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
        self.date_done = datetime.now(timezone.utc)

    def mark_as_failed(
        self,
        exception_name: str | None = None,
        exception_message: str | None = None,
        exception_info: str | None = None,
    ):
        """Mark task as failed"""
        self.state = QueuedTaskState.failed
        self.date_failed = datetime.now(timezone.utc)
        if exception_name:
            self.exception_name = exception_name
        if exception_message:
            self.exception_message = exception_message
        if exception_info:
            self.exception_info = exception_info

    def mark_as_stopped(self):
        """Mark task as stopped"""
        self.state = QueuedTaskState.stopped
        self.date_stopped = datetime.now(timezone.utc)

    def mark_as_cancelled(self):
        """Mark task as cancelled"""
        self.state = QueuedTaskState.cancelled
        self.date_cancelled = datetime.now(timezone.utc)

    def mark_as_waiting(self):
        """Mark task as waiting"""
        self.state = QueuedTaskState.waiting

    def restart(self):
        """Reset task to queue by resetting all state fields"""
        self.state = QueuedTaskState.enqueued
        self.date_enqueued = datetime.now(timezone.utc)
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
        self.retry_count = 0

    @property
    def is_finished(self) -> bool:
        """Check if task is in a final state"""
        return hasattr(self, "state") and self.state in [
            QueuedTaskState.done,
            QueuedTaskState.failed,
            QueuedTaskState.cancelled,
        ]

    @property
    def is_active(self) -> bool:
        """Check if task is active (running or waiting)"""
        return hasattr(self, "state") and self.state in [
            QueuedTaskState.enqueued,
            QueuedTaskState.waiting,
            QueuedTaskState.doing,
        ]

    @property
    def can_be_restarted(self) -> bool:
        """Check if task can be restarted"""
        return hasattr(self, "state") and self.state in [
            QueuedTaskState.stopped,
            QueuedTaskState.failed,
        ]

    @property
    def can_be_cancelled(self) -> bool:
        """Check if task can be cancelled"""
        return hasattr(self, "state") and self.state in [
            QueuedTaskState.enqueued,
            QueuedTaskState.waiting,
            QueuedTaskState.doing,
        ]
