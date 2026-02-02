# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging

from datetime import datetime
from typing import cast

from fastedgy import context
from fastedgy.dependencies import get_service
from fastedgy.queued_task.context import get_current_task
from fastedgy.queued_task.config import QueuedTaskConfig


class QueuedTaskLogger(logging.Logger):
    """
    Custom logger that extends standard Python logging with database logging.

    When a QueuedTask is available in context, logs are also saved to QueuedTaskLog table.
    Maintains full compatibility with standard logging.Logger interface.
    """

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)
        self._config: QueuedTaskConfig | None = None

    @property
    def config(self) -> QueuedTaskConfig:
        if self._config is None:
            self._config = get_service(QueuedTaskConfig)

        return self._config

    def _log_to_db_sync(self, level: str, message: str, *args, **kwargs) -> None:
        """Synchronous wrapper for database logging"""
        try:
            loop = asyncio.get_running_loop()

            if loop and not loop.is_closed():
                asyncio.create_task(
                    self._log_to_db_async(level, message, *args, **kwargs)
                )
        except RuntimeError:
            # No event loop available - skip database logging silently
            pass

    async def _log_to_db_async(self, level: str, message: str, *args, **kwargs) -> None:
        """Asynchronous database logging"""
        if not self.config.enable_db_logging:
            return

        task = get_current_task()

        if task is None:
            return

        try:
            from fastedgy.orm import Registry
            from fastedgy.models.queued_task_log import (
                BaseQueuedTaskLog as QueuedTaskLog,
            )
            from fastedgy.queued_task.models.queued_task_log import QueuedTaskLogType
            from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask

            log_type = QueuedTaskLogType[level.lower()]

            # Use manager registry if available (separate DB connection for queue operations)
            # to avoid transaction conflicts with the main application database
            manager_registry = self.config.get_manager_registry()
            if manager_registry is not None:
                registry = manager_registry
            else:
                registry = get_service(Registry)

            QTL = cast(type["QueuedTaskLog"], registry.get_model("QueuedTaskLog"))
            QT = cast(type["QueuedTask"], registry.get_model("QueuedTask"))

            if args:
                try:
                    formatted_message = message % args
                except (TypeError, ValueError):
                    formatted_message = f"{message} {args}"
            else:
                formatted_message = message

            task_id = task.id if hasattr(task, "id") else None
            if task_id:
                existing_task = await QT.query.filter(
                    QT.columns.id == task_id
                ).get_or_none()
                if not existing_task:
                    return

            queued_task_log = QTL(
                task=task,
                log_type=log_type,
                name=self.name,
                message=formatted_message,
                info=str(kwargs) if kwargs else None,
                logged_at=datetime.now(context.get_timezone()),
            )

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await queued_task_log.save()
                    break
                except Exception as retry_error:
                    error_type_name = type(retry_error).__name__
                    error_message = str(retry_error).lower()

                    if (
                        "foreign key constraint" in error_message
                        or "ForeignKeyViolationError" in error_type_name
                    ):
                        return

                    if (
                        "SerializationError" in error_type_name
                        or "serialization" in error_message
                    ):
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.1 * (attempt + 1))
                            continue
                        return

                    if (
                        "NoActiveSQLTransactionError" in error_type_name
                        or "savepoint" in error_message.lower()
                    ):
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.1 * (attempt + 1))
                            continue
                        return

                    raise

        except Exception as e:
            error_type_name = type(e).__name__
            error_message = str(e).lower()

            if (
                "foreign key constraint" in error_message
                or "ForeignKeyViolationError" in error_type_name
                or "SerializationError" in error_type_name
                or "serialization" in error_message
            ):
                return

            super().error(f"Failed to log to database: {e}", exc_info=False)

    def _log_with_db(self, level: int, message: str, *args, **kwargs) -> None:
        """Enhanced logging that includes database logging"""
        if self.config.enable_dual_logging or get_current_task() is None:
            super()._log(level, message, args, **kwargs)

        level_name = logging.getLevelName(level)
        self._log_to_db_sync(level_name, message, *args, **kwargs)

    def debug(self, message: str, *args, **kwargs) -> None:
        """Log debug message"""
        if self.isEnabledFor(logging.DEBUG):
            self._log_with_db(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        """Log info message"""
        if self.isEnabledFor(logging.INFO):
            self._log_with_db(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        """Log warning message"""
        if self.isEnabledFor(logging.WARNING):
            self._log_with_db(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        """Log error message"""
        if self.isEnabledFor(logging.ERROR):
            self._log_with_db(logging.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs) -> None:
        """Log critical message"""
        if self.isEnabledFor(logging.CRITICAL):
            self._log_with_db(logging.CRITICAL, message, *args, **kwargs)

    def exception(self, message: str, *args, exc_info=True, **kwargs) -> None:
        """Log exception with traceback"""
        if self.isEnabledFor(logging.ERROR):
            self._log_with_db(
                logging.ERROR, message, *args, exc_info=exc_info, **kwargs
            )


logging.setLoggerClass(QueuedTaskLogger)


def getLogger(name: str | None = None) -> QueuedTaskLogger:
    """
    Get a QueuedTaskLogger instance

    Drop-in replacement for logging.getLogger() with enhanced database logging
    when QueuedTask is available in context.

    Args:
        name: Logger name (same as logging.getLogger)

    Returns:
        QueuedTaskLogger instance with enhanced capabilities
    """
    logger = logging.getLogger(name)

    if not isinstance(logger, QueuedTaskLogger):
        logger.__class__ = QueuedTaskLogger

    return cast(QueuedTaskLogger, logger)
