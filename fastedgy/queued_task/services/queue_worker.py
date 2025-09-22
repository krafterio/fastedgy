# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

import dill

import importlib

import logging

import traceback

from datetime import datetime
import random

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.queued_task.config import QueuedTaskConfig
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.queued_task.context import TaskContext
from fastedgy.queued_task.services.queue_hooks import QueueHookRegistry

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


logger = logging.getLogger("queued_task.worker")
logger.setLevel(logging.DEBUG)


class QueueWorker:
    """Individual worker that executes a single task"""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.current_task: Optional[QueuedTask] = None
        self.is_busy = False
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.hook_registry = get_service(QueueHookRegistry)
        self.config = get_service(QueuedTaskConfig)

    async def run_task(self, task: "QueuedTask") -> Dict[str, Any]:
        """
        Execute a single queued task.

        Args:
            task: The QueuedTask to execute

        Returns:
            Dictionary with execution results
        """
        self.current_task = task
        self.is_busy = True
        self.last_activity = datetime.now()

        QueuedTask = cast(
            type["QueuedTask"], get_service(Registry).get_model("QueuedTask")
        )

        try:
            logger.info(
                f"Worker {self.worker_id} starting task {task.id}: {task.module_name}.{task.function_name}"
            )

            # FIRST CHECK: Verify parent is still valid before starting
            if task.parent_task:
                parent = await QueuedTask.query.filter(
                    QueuedTask.columns.id == task.parent_task.id
                ).get_or_none()

                if not parent or parent.state != QueuedTaskState.done:
                    parent_state = parent.state if parent else "not_found"
                    logger.warning(
                        f"Parent task {task.parent_task.id} is {parent_state}, aborting child {task.id}"
                    )
                    task.mark_as_failed(
                        exception_name="ParentTaskNotReady",
                        exception_message=f"Parent task {task.parent_task.id} is {parent_state}",
                        exception_info="Parent task is not in 'done' state, cannot execute child",
                    )
                    await task.save()

                    return {
                        "status": "error",
                        "error": f"Parent task {task.parent_task.id} not ready",
                        "worker_id": self.worker_id,
                        "task_id": task.id,
                    }

            # Run pre/post hooks + execution under a dedicated connection to avoid
            # reentrancy with ORM implicit transactions
            from fastedgy.orm import Database as EdgyDatabase  # type: ignore

            database: EdgyDatabase = get_service(EdgyDatabase)
            async with database.connection():
                await self.hook_registry.trigger_pre_run(task)

                logger.debug(f"Executing task function for task {task.id}")
                result = await self._execute_task_function(task)
                logger.debug(f"Task {task.id} execution result: {result}")

                await self.hook_registry.trigger_post_run(task, result=result)

            # Check if parent task is still valid before marking as done
            if task.parent_task:
                parent = await QueuedTask.query.filter(
                    QueuedTask.columns.id == task.parent_task.id
                ).get_or_none()

                if parent and parent.state != QueuedTaskState.done:
                    # Parent failed/cancelled while we were executing, mark as failed
                    logger.warning(
                        f"Parent task {parent.id} is {parent.state}, marking child {task.id} as failed"
                    )
                    task.mark_as_failed(
                        exception_name="ParentTaskFailed",
                        exception_message=f"Parent task {parent.id} is {parent.state}",
                        exception_info=f"Parent task changed state to {parent.state} during child execution",
                    )
                    await task.save()

                    return {
                        "status": "error",
                        "error": f"Parent task {parent.id} failed",
                        "worker_id": self.worker_id,
                        "task_id": task.id,
                    }

            async def _op_mark_done():
                logger.debug(f"Marking task {task.id} as done [raw]")
                from sqlalchemy import text
                from fastedgy.orm import Database as EdgyDatabase  # type: ignore

                database: EdgyDatabase = get_service(EdgyDatabase)
                sql = text(
                    "UPDATE queued_tasks SET state = 'done'::queuedtaskstate,\n"
                    "    date_done = NOW(),\n"
                    "    date_ended = NOW(),\n"
                    "    execution_time = EXTRACT(EPOCH FROM (NOW() - COALESCE(date_started, NOW()))),\n"
                    "    updated_at = NOW()\n"
                    "WHERE id = :id"
                )
                await database.execute(sql, {"id": task.id})

            await self._run_write_with_retry(_op_mark_done)

            logger.info(
                f"Worker {self.worker_id} completed task {task.id} successfully"
            )

            return {
                "status": "success",
                "result": result,
                "worker_id": self.worker_id,
                "task_id": task.id,
            }

        except Exception as e:
            # 4) Best-effort set task as failed with retry
            async def _op_mark_failed():
                from sqlalchemy import text
                from fastedgy.orm import Database as EdgyDatabase  # type: ignore

                database: EdgyDatabase = get_service(EdgyDatabase)
                sql = text(
                    "UPDATE queued_tasks SET state = 'failed'::queuedtaskstate,\n"
                    "    exception_name = :name,\n"
                    "    exception_message = :message,\n"
                    "    exception_info = :info,\n"
                    "    date_failed = NOW(),\n"
                    "    date_ended = NOW(),\n"
                    "    execution_time = EXTRACT(EPOCH FROM (NOW() - COALESCE(date_started, NOW()))),\n"
                    "    updated_at = NOW()\n"
                    "WHERE id = :id"
                )
                await database.execute(
                    sql,
                    {
                        "id": task.id,
                        "name": type(e).__name__,
                        "message": str(e),
                        "info": traceback.format_exc(),
                    },
                )

            try:
                await self._run_write_with_retry(_op_mark_failed)
            except Exception as save_err:
                logger.error(
                    f"Failed to persist failure state for task {getattr(task, 'id', '?')}: {save_err}"
                )

            # Try to run error hook but don't fail the whole worker if it errors
            try:
                await self.hook_registry.trigger_post_run(task, error=e)
            except Exception as hook_err:
                logger.error(
                    f"post_run hook failed for task {getattr(task, 'id', '?')}: {hook_err}"
                )

            logger.error(f"Worker {self.worker_id} failed task {task.id}: {e}")

            return {
                "status": "error",
                "error": str(e),
                "worker_id": self.worker_id,
                "task_id": task.id,
            }

        finally:
            self.current_task = None
            self.is_busy = False
            self.last_activity = datetime.now()

    async def _execute_task_function(self, task: "QueuedTask") -> Any:
        """Load and execute the task function with proper context"""

        # Load function: either from module or from serialized data
        if task.serialized_function:
            # Deserialize local function with dill
            logger.debug(f"Deserializing local function for task {task.id}")
            try:
                func = dill.loads(task.serialized_function)
                logger.debug(
                    f"Function deserialized: {func}, is_coroutine: {asyncio.iscoroutinefunction(func)}"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to deserialize function: {e}")
        else:
            # Load from module
            logger.debug(
                f"Loading module '{task.module_name}' and function '{task.function_name}'"
            )
            try:
                module = importlib.import_module(str(task.module_name))
                logger.debug(f"Module loaded: {module}")
                func = getattr(module, str(task.function_name))
                logger.debug(
                    f"Function loaded: {func}, is_coroutine: {asyncio.iscoroutinefunction(func)}"
                )
            except ImportError as e:
                raise ImportError(f"Cannot import module '{task.module_name}': {e}")
            except AttributeError as e:
                raise AttributeError(
                    f"Function '{task.function_name}' not found in module '{task.module_name}': {e}"
                )

        if not callable(func):
            func_name = getattr(func, "__name__", "unnamed")
            raise TypeError(f"'{func_name}' is not callable")

        # Set up task context
        execution_context = task.context.copy() if task.context else {}
        logger.debug(f"Task context: {execution_context}")

        # Use TaskContext to manage current task and execution context
        with TaskContext(task, execution_context):
            try:
                # Prepare arguments
                args = task.args or []
                kwargs = task.kwargs or {}
                logger.debug(f"Args: {args}, Kwargs: {kwargs}")

                # Execute function (sync or async)
                if asyncio.iscoroutinefunction(func):
                    logger.debug("Executing async function")
                    result = await func(*args, **kwargs)
                    logger.debug(f"Async function result: {result}")
                else:
                    logger.debug("Executing sync function in executor")
                    # Run sync function in thread pool to avoid blocking
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: func(*args, **kwargs)
                    )
                    logger.debug(f"Sync function result: {result}")

                return result

            except Exception:
                # Exception will be handled and logged by the caller (run_task)
                raise

    @property
    def is_idle_timeout(self) -> bool:
        """Check if worker has been idle for too long"""
        if self.is_busy:
            return False

        idle_duration = (datetime.now() - self.last_activity).total_seconds()
        return idle_duration > self.config.worker_idle_timeout

    def __str__(self):
        return f"QueueWorker({self.worker_id}, busy={self.is_busy})"

    def __repr__(self):
        return self.__str__()

    async def _run_write_with_retry(
        self, op_coro_factory, *, max_attempts: int = 3, base_delay: float = 0.05
    ):
        """Run a small DB write with retries under a short-lived connection to avoid transaction reentrancy."""
        from sqlalchemy.exc import DBAPIError, OperationalError
        from fastedgy.orm import Database as EdgyDatabase  # type: ignore

        database: EdgyDatabase = get_service(EdgyDatabase)

        attempt = 0
        while True:
            try:
                async with database.connection():
                    await op_coro_factory()
                return
            except (DBAPIError, OperationalError) as e:  # type: ignore
                if self._is_retryable_db_error(e) and attempt < max_attempts - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, base_delay)
                    logger.debug(
                        f"Transient DB error, retry {attempt + 1}/{max_attempts} in {delay:.3f}s"
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                # Final failure: surface as warning before raising
                logger.warning(f"DB write failed after {attempt + 1} attempts: {e}")
                raise

    def _is_retryable_db_error(self, exc: Exception) -> bool:
        """Detect Postgres serialization/deadlock errors in a driver-agnostic way."""
        txt = str(exc).lower()
        if "could not serialize access" in txt:
            return True
        if "deadlock detected" in txt:
            return True
        # Try to inspect underlying DBAPI error
        orig = getattr(exc, "orig", None)
        if orig is not None:
            txt2 = str(orig).lower()
            if "could not serialize access" in txt2 or "deadlock detected" in txt2:
                return True
            sqlstate = getattr(orig, "sqlstate", None) or getattr(
                orig, "sql_state", None
            )
            if sqlstate in ("40001", "40P01"):
                return True
        return False
