# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import socket

from datetime import datetime

from typing import Optional

from fastedgy.orm import Model, fields


class QueuedTaskWorkerMixin(Model):
    """
    Mixin for tracking queue workers status across multiple servers/instances
    """

    class Meta:
        abstract = True
        label = "Worker des tâches en file d'attente"
        label_plural = "Workers des tâches en file d'attente"
        unique_together = [("server_name",)]
        indexes = [
            fields.Index(fields=["is_running", "last_heartbeat"], name="idx_queued_task_workers_running_heartbeat"),
            fields.Index(fields=["server_name"], name="idx_queued_task_workers_server"),
            fields.Index(fields=["last_heartbeat"], name="idx_queued_task_workers_heartbeat"),
        ]

    server_name: str = fields.CharField(max_length=255, default=lambda: socket.gethostname(), label="Server Name")
    max_workers: int = fields.IntegerField(default=1, label="Max Workers")
    active_workers: int = fields.IntegerField(default=0, label="Active Workers")
    idle_workers: int = fields.IntegerField(default=0, label="Idle Workers")
    is_running: bool = fields.BooleanField(default=False, label="Is Running")
    last_heartbeat: datetime = fields.DateTimeField(auto_now=True, label="Last Heartbeat")
    started_at: Optional[datetime] = fields.DateTimeField(null=True, label="Started At")
    version: Optional[str] = fields.CharField(max_length=50, null=True, label="Version")

    @property
    def total_workers(self) -> int:
        """Total workers in this server's pool"""
        return self.active_workers + self.idle_workers

    @property
    def is_alive(self) -> bool:
        """Check if server is alive (heartbeat within last 2 minutes)"""
        if not self.last_heartbeat:
            return False
        return (datetime.now() - self.last_heartbeat).total_seconds() < 120

    def update_stats(self, active: int, idle: int, is_running: bool = True):
        """Update worker statistics"""
        self.active_workers = active
        self.idle_workers = idle
        self.is_running = is_running
        self.last_heartbeat = datetime.now()

    def mark_as_started(self, max_workers: int):
        """Mark server as started"""
        self.max_workers = max_workers
        self.is_running = True
        self.started_at = datetime.now()
        self.last_heartbeat = datetime.now()

    def mark_as_stopped(self):
        """Mark server as stopped"""
        self.is_running = False
        self.active_workers = 0
        self.idle_workers = 0
        self.last_heartbeat = datetime.now()
