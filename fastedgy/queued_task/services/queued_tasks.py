# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Callable,
    ParamSpec,
    cast,
    Protocol,
)

from datetime import datetime

from dataclasses import dataclass

import asyncio

import dill

import json

import logging

from fastedgy.dependencies import Inject
from fastedgy.orm import Registry
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.queued_task.services.queued_task_ref import QueuedTaskRef
from fastedgy.queued_task.services.queue_hooks import QueueHookRegistry


if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


P = ParamSpec("P")
logger = logging.getLogger("queued_tasks")


class SerializableCallable(Protocol):
    """Protocol for functions that can be serialized for queues tasks"""

    __module__: str
    __name__: str

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass
class TaskCreationRequest:
    """Request for creating a task in the creation queue"""

    ref: "QueuedTaskRef"
    func: Callable
    args: List[Any]
    kwargs: Dict[str, Any]
    parent_ref: Optional["QueuedTaskRef"] = None

    def __post_init__(self):
        if self.args is None:
            self.args = []
        if self.kwargs is None:
            self.kwargs = {}


class QueuedTasks:
    """Queued task management service."""

    def __init__(
        self,
        hook_registry: QueueHookRegistry = Inject(QueueHookRegistry),
        registry: Registry = Inject(Registry),
    ):
        self._creation_queue: List[TaskCreationRequest] = []
        self._creation_task: Optional[asyncio.Task] = None
        self.hook_registry = hook_registry
        self.registry = registry

    def add_task(
        self,
        func: Callable[P, Any],
        *args: P.args,
        parent: QueuedTaskRef | None = None,
        **kwargs: P.kwargs,
    ) -> QueuedTaskRef:
        """
        Add task to queue - supports both regular functions and local functions.
        Returns a QueuedTaskRef for task control and dependency management.
        """
        if "QueuedTask" not in self.registry.models:
            raise RuntimeError(
                "QueuedTask feature is not configured. "
                "Please add QueuedTask, QueuedTaskLog, and QueuedTaskWorker models to your project."
            )

        # Validation: No instance methods
        if hasattr(func, "__self__"):
            raise ValueError(f"Instance methods are not supported: {func}")

        # Validation: Serializable arguments
        try:
            json.dumps({"args": args, "kwargs": kwargs})
        except (TypeError, ValueError) as e:
            raise ValueError(f"Non-serializable arguments for {func.__name__}: {e}")

        # Create task reference
        task_ref = QueuedTaskRef(self)

        # Create creation request
        creation_request = TaskCreationRequest(
            ref=task_ref,
            func=func,
            args=list(args),
            kwargs=dict(kwargs),
            parent_ref=parent,
        )

        # Add to creation queue
        self._creation_queue.append(creation_request)

        # Start creation processor if not already running
        if not self._creation_task or self._creation_task.done():
            self._creation_task = asyncio.create_task(self._process_creation_queue())

        return task_ref

    async def _process_creation_queue(self) -> None:
        """Process the task creation queue, resolving dependencies in correct order"""
        try:
            while self._creation_queue:
                # Take all current requests
                requests = self._creation_queue.copy()
                self._creation_queue.clear()

                if not requests:
                    break

                # Separate requests: no parent vs with parent
                no_parent_requests = [r for r in requests if r.parent_ref is None]
                with_parent_requests = [r for r in requests if r.parent_ref is not None]

                # 1. Create tasks without parents first
                for request in no_parent_requests:
                    try:
                        task_id = await self._create_task_for_request(request)
                        request.ref._set_task_id(task_id)
                        logger.debug(f"Created task {task_id} (no parent)")
                    except Exception as e:
                        logger.error(f"Failed to create task: {e}")
                        request.ref._set_creation_error(e)

                # 2. Create tasks with parents (after parent IDs are resolved)
                for request in with_parent_requests:
                    try:
                        if request.parent_ref:
                            # Wait for parent to be created
                            parent_id = await request.parent_ref.get_task_id()
                            task_id = await self._create_task_for_request(
                                request, parent_id
                            )
                            request.ref._set_task_id(task_id)
                            logger.debug(
                                f"Created task {task_id} (parent: {parent_id})"
                            )
                    except Exception as e:
                        logger.error(f"Failed to create task with parent: {e}")
                        request.ref._set_creation_error(e)

        except Exception as e:
            logger.error(f"Error in creation queue processor: {e}")
        finally:
            self._creation_task = None

    async def _create_task_for_request(
        self, request: TaskCreationRequest, parent_id: Optional[int] = None
    ) -> int:
        """Create a task in database from a creation request"""
        func = request.func
        args = request.args
        kwargs = request.kwargs

        # Determine if function can be imported normally
        is_local_function = False
        module_name = None
        function_name = None
        serialized_function = None

        if hasattr(func, "__module__") and hasattr(func, "__name__"):
            try:
                # Test if function can be imported
                import importlib

                module = importlib.import_module(func.__module__)
                getattr(module, func.__name__)
                # If we reach here, function is importable
                module_name = func.__module__
                function_name = func.__name__
            except (ImportError, AttributeError):
                # Function is local or not importable, use dill
                is_local_function = True
        else:
            # Function doesn't have module/name, must serialize
            is_local_function = True

        if is_local_function:
            # Serialize the function with dill
            serialized_function = dill.dumps(func)

        # Get parent task if specified
        parent_task = None
        if parent_id:
            parent_task = await self.get_task_by_id(parent_id)
            if not parent_task:
                raise ValueError(f"Parent task {parent_id} not found")

        # Create the task
        task = await self.create_task(
            module_name=module_name,
            function_name=function_name,
            serialized_function=serialized_function,
            args=args,
            kwargs=kwargs,
            parent_task=parent_task,
        )

        return task.id or 0

    async def add_task_async(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> "QueuedTask":
        """
        Async version of add_task - creates task immediately and returns it
        """
        if "QueuedTask" not in self.registry.models:
            raise RuntimeError(
                "QueuedTask feature is not configured. "
                "Please add QueuedTask, QueuedTaskLog, and QueuedTaskWorker models to your project."
            )

        # Validation: No instance methods
        if hasattr(func, "__self__"):
            raise ValueError(f"Instance methods are not supported: {func}")

        # Validation: Serializable arguments
        try:
            json.dumps({"args": args, "kwargs": kwargs})
        except (TypeError, ValueError) as e:
            raise ValueError(f"Non-serializable arguments for {func.__name__}: {e}")

        serializable_func = cast(SerializableCallable, func)
        return await self._create_queued_task(serializable_func, args, kwargs)

    async def _create_queued_task(
        self, func: SerializableCallable, args: tuple, kwargs: dict
    ):
        """Create queued task - supports both regular and local functions"""
        try:
            # Try to determine if function can be imported normally
            is_local_function = False
            module_name = None
            function_name = None
            serialized_function = None

            if hasattr(func, "__module__") and hasattr(func, "__name__"):
                try:
                    # Test if function can be imported
                    import importlib

                    module = importlib.import_module(func.__module__)
                    getattr(module, func.__name__)
                    # If we reach here, function is importable
                    module_name = func.__module__
                    function_name = func.__name__
                except (ImportError, AttributeError):
                    # Function is local or not importable, use dill
                    is_local_function = True
            else:
                # Function doesn't have module/name, must serialize
                is_local_function = True

            if is_local_function:
                # Serialize the function with dill
                serialized_function = dill.dumps(func)
                logger.debug(
                    f"Serialized local function: {getattr(func, '__name__', 'unnamed')}"
                )

            task = await self.create_task(
                module_name=module_name,
                function_name=function_name,
                serialized_function=serialized_function,
                args=list(args),
                kwargs=dict(kwargs),
            )

            return task
        except Exception as e:
            func_name = getattr(func, "__name__", "unnamed")
            logger.error(f"Error creating queued task for {func_name}: {e}")
            raise

    async def create_task(
        self,
        module_name: Optional[str] = None,
        function_name: Optional[str] = None,
        serialized_function: Optional[bytes] = None,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        parent_task: Optional["QueuedTask"] = None,
    ) -> "QueuedTask":
        """Create a new task in the queue"""
        # Validation: must have either module/function or serialized function
        if not serialized_function and (not module_name or not function_name):
            raise ValueError(
                "Must provide either (module_name, function_name) or serialized_function"
            )

        QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))
        task = QueuedTask(
            name=name,
            module_name=module_name,
            function_name=function_name,
            serialized_function=serialized_function,
            args=args or [],
            kwargs=kwargs or {},
            context=context or {},
            parent_task=parent_task,
            state=QueuedTaskState.enqueued,
            date_enqueued=datetime.now(),
        )

        await self.hook_registry.trigger_pre_create(task)

        await task.save()

        await self.hook_registry.trigger_post_create(task)

        return task

    async def create_child_task(
        self,
        parent_task_id: int,
        module_name: Optional[str] = None,
        function_name: Optional[str] = None,
        serialized_function: Optional[bytes] = None,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> "QueuedTask":
        """Create a child task that depends on a parent task"""
        parent_task = await self.get_task_by_id(parent_task_id)
        if not parent_task:
            raise ValueError(f"Parent task {parent_task_id} not found")

        return await self.create_task(
            module_name=module_name,
            function_name=function_name,
            serialized_function=serialized_function,
            args=args,
            kwargs=kwargs,
            context=context,
            name=name,
            parent_task=parent_task,
        )

    async def add_child_task_async(
        self,
        parent_task_id: int,
        func: Callable[P, Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> "QueuedTask":
        """Add a child task using a function (async version)"""
        parent_task = await self.get_task_by_id(parent_task_id)
        if not parent_task:
            raise ValueError(f"Parent task {parent_task_id} not found")

        # Validation: No instance methods
        if hasattr(func, "__self__"):
            raise ValueError(f"Instance methods are not supported: {func}")

        # Validation: Serializable arguments
        try:
            json.dumps({"args": args, "kwargs": kwargs})
        except (TypeError, ValueError) as e:
            raise ValueError(f"Non-serializable arguments for {func.__name__}: {e}")

        # Try to determine if function can be imported normally
        is_local_function = False
        module_name = None
        function_name = None
        serialized_function = None

        if hasattr(func, "__module__") and hasattr(func, "__name__"):
            try:
                # Test if function can be imported
                import importlib

                module = importlib.import_module(func.__module__)
                getattr(module, func.__name__)
                # If we reach here, function is importable
                module_name = func.__module__
                function_name = func.__name__
            except (ImportError, AttributeError):
                # Function is local or not importable, use dill
                is_local_function = True
        else:
            # Function doesn't have module/name, must serialize
            is_local_function = True

        if is_local_function:
            # Serialize the function with dill
            serialized_function = dill.dumps(func)

        return await self.create_task(
            module_name=module_name,
            function_name=function_name,
            serialized_function=serialized_function,
            args=list(args),
            kwargs=dict(kwargs),
            parent_task=parent_task,
        )

    async def retry_task(self, task_id: int) -> "QueuedTask":
        """
        Retry a task by ID. If task is done/failed/cancelled, clone it.
        If task is stopped, just re-enqueue it.

        Args:
            task_id: ID of the task to retry

        Returns:
            QueuedTask: The retried task (original or cloned)
        """
        task = await self.get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.state == QueuedTaskState.enqueued:
            raise ValueError(f"Task {task_id} is already enqueued")
        elif task.state == QueuedTaskState.doing:
            raise ValueError(f"Task {task_id} is currently running")
        elif task.state == QueuedTaskState.stopped:
            # Just re-enqueue the existing task
            task.state = QueuedTaskState.enqueued
            task.date_enqueued = datetime.now()
            task.date_started = None
            task.date_stopped = None
            task.exception_name = None
            task.exception_message = None
            task.exception_info = None
            await task.save()
            return task
        else:
            # Clone the task for done/failed/cancelled states
            QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))
            cloned_task = QueuedTask(
                name=f"{task.name}_retry",
                module_name=task.module_name,
                function_name=task.function_name,
                args=task.args,
                kwargs=task.kwargs,
                context=task.context.copy() if task.context else {},
                parent_task=task.parent_task,
                state=QueuedTaskState.enqueued,
                date_enqueued=datetime.now(),
            )
            await cloned_task.save()
            return cloned_task

    async def get_pending_tasks_count(self) -> int:
        """Count pending tasks"""
        return await QueuedTask.query.filter(
            QueuedTask.columns.state == QueuedTaskState.enqueued
        ).count()

    async def get_task_by_id(self, task_id: int) -> Optional["QueuedTask"]:
        """Get task by ID"""
        return await QueuedTask.query.filter(
            QueuedTask.columns.id == task_id
        ).get_or_none()

    async def get_task_status(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get task status"""
        task = await self.get_task_by_id(task_id)

        if not task:
            return None

        return {
            "id": task.id,
            "name": task.name,
            "module_name": task.module_name,
            "function_name": task.function_name,
            "state": task.state,
            "args": task.args,
            "kwargs": task.kwargs,
            "context": task.context,
            "execution_time": task.execution_time,
            "exception_name": task.exception_name,
            "exception_message": task.exception_message,
            "created_at": task.created_at,
            "date_enqueued": task.date_enqueued,
            "date_started": task.date_started,
            "date_ended": task.date_ended,
            "parent_task": task.parent_task.id if task.parent_task else None,
            "is_finished": task.is_finished,
            "is_active": task.is_active,
            "can_be_restarted": task.can_be_restarted,
            "can_be_cancelled": task.can_be_cancelled,
        }
