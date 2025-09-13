# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

import dill

import importlib

import logging

import traceback

from datetime import datetime

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.queued_task.config import QueuedTaskConfig
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.queued_task.context import TaskContext
from fastedgy.queued_task.services.queue_hooks import QueueHookRegistry

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


logger = logging.getLogger('queued_task.worker')
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

        QueuedTask = cast(type["QueuedTask"], get_service(Registry).get_model("QueuedTask"))

        try:
            logger.info(f"Worker {self.worker_id} starting task {task.id}: {task.module_name}.{task.function_name}")

            # FIRST CHECK: Verify parent is still valid before starting
            if task.parent_task:
                parent = await QueuedTask.query.filter(
                    QueuedTask.columns.id == task.parent_task.id
                ).get_or_none()

                if not parent or parent.state != QueuedTaskState.done:
                    parent_state = parent.state if parent else "not_found"
                    logger.warning(f"Parent task {task.parent_task.id} is {parent_state}, aborting child {task.id}")
                    task.mark_as_failed(
                        exception_name="ParentTaskNotReady",
                        exception_message=f"Parent task {task.parent_task.id} is {parent_state}",
                        exception_info="Parent task is not in 'done' state, cannot execute child"
                    )
                    await task.save()

                    return {
                        "status": "error",
                        "error": f"Parent task {task.parent_task.id} not ready",
                        "worker_id": self.worker_id,
                        "task_id": task.id
                    }

            # Mark task as doing
            logger.debug(f"Marking task {task.id} as doing")
            task.mark_as_doing()
            await task.save()

            await self.hook_registry.trigger_pre_run(task)

            # Load and execute the function
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
                    logger.warning(f"Parent task {parent.id} is {parent.state}, marking child {task.id} as failed")
                    task.mark_as_failed(
                        exception_name="ParentTaskFailed",
                        exception_message=f"Parent task {parent.id} is {parent.state}",
                        exception_info=f"Parent task changed state to {parent.state} during child execution"
                    )
                    await task.save()

                    return {
                        "status": "error",
                        "error": f"Parent task {parent.id} failed",
                        "worker_id": self.worker_id,
                        "task_id": task.id
                    }

            # Mark task as done
            logger.debug(f"Marking task {task.id} as done")
            task.mark_as_done()
            await task.save()


            logger.info(f"Worker {self.worker_id} completed task {task.id} successfully")

            return {
                "status": "success",
                "result": result,
                "worker_id": self.worker_id,
                "task_id": task.id
            }

        except Exception as e:
            # Mark task as failed
            task.mark_as_failed(
                exception_name=type(e).__name__,
                exception_message=str(e),
                exception_info=traceback.format_exc()
            )
            await task.save()

            await self.hook_registry.trigger_post_run(task, error=e)

            logger.error(f"Worker {self.worker_id} failed task {task.id}: {e}")

            return {
                "status": "error",
                "error": str(e),
                "worker_id": self.worker_id,
                "task_id": task.id
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
                logger.debug(f"Function deserialized: {func}, is_coroutine: {asyncio.iscoroutinefunction(func)}")
            except Exception as e:
                raise RuntimeError(f"Failed to deserialize function: {e}")
        else:
            # Load from module
            logger.debug(f"Loading module '{task.module_name}' and function '{task.function_name}'")
            try:
                module = importlib.import_module(str(task.module_name))
                logger.debug(f"Module loaded: {module}")
                func = getattr(module, str(task.function_name))
                logger.debug(f"Function loaded: {func}, is_coroutine: {asyncio.iscoroutinefunction(func)}")
            except ImportError as e:
                raise ImportError(f"Cannot import module '{task.module_name}': {e}")
            except AttributeError as e:
                raise AttributeError(f"Function '{task.function_name}' not found in module '{task.module_name}': {e}")

        if not callable(func):
            func_name = getattr(func, '__name__', 'unnamed')
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
