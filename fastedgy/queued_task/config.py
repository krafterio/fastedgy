# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

from fastedgy.dependencies import register_service


class QueuedTaskConfig:
    # Logging configuration
    enable_db_logging: bool = True
    enable_dual_logging: bool = True

    # Worker configuration
    max_workers: int = int(os.environ.get('QUEUED_TASK_MAX_WORKERS', os.cpu_count() or 1))
    worker_idle_timeout: int = int(os.environ.get('QUEUED_TASK_WORKER_IDLE_TIMEOUT', 60))  # seconds

    # Manager configuration
    polling_interval: int = int(os.environ.get('QUEUED_TASK_POLLING_INTERVAL', 2))  # seconds
    fallback_polling_interval: int = int(os.environ.get('QUEUED_TASK_FALLBACK_POLLING_INTERVAL', 30))  # seconds

    # Task execution configuration
    task_timeout: int = int(os.environ.get('QUEUED_TASK_TIMEOUT', 300))  # 5 minutes default
    max_retries: int = int(os.environ.get('QUEUED_TASK_MAX_RETRIES', 3))

    # Notification configuration
    use_postgresql_notify: bool = bool(os.environ.get('QUEUED_TASK_USE_POSTGRESQL_NOTIFY', 'true').lower() == 'true')
    notify_channel: str = os.environ.get('QUEUED_TASK_NOTIFY_CHANNEL', 'queued_new_task')


register_service(lambda: QueuedTaskConfig(), QueuedTaskConfig)
