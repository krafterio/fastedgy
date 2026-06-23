# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

from typing import Optional, Any, TYPE_CHECKING

from fastedgy.queued_task.models.queued_task import QueuedTaskState

if TYPE_CHECKING:
    from fastedgy.queued_task.services.queued_tasks import QueuedTasks


class QueuedTaskRef:
    """
    Reference to a queued task that allows control operations.
    The task may not be created in database yet.
    """

    def __init__(self, service: "QueuedTasks"):
        self._service = service
        self._task_id: Optional[int] = None
        self._creation_future: Optional[asyncio.Future[int]] = asyncio.Future()

    @property
    def id(self) -> Optional[int]:
        """Task ID (None if not yet created in database)"""
        return self._task_id

    async def get_task_id(self) -> int:
        """Wait for task to be created in database and return ID"""
        if self._task_id is not None:
            return self._task_id

        if self._creation_future and not self._creation_future.done():
            return await self._creation_future

        if self._task_id is not None:
            return self._task_id

        raise RuntimeError("Task creation failed or was cancelled")

    async def cancel(self) -> None:
        """Cancel this task.

        Awaited directly (no fire-and-forget): errors propagate to the
        caller instead of being silently lost in a background task.
        """
        await self._cancel_async()

    async def stop(self) -> None:
        """Stop this task if running.

        Awaited directly (no fire-and-forget): errors propagate to the
        caller instead of being silently lost in a background task.
        """
        await self._stop_async()

    async def wait(self, timeout: Optional[float] = None) -> Any:
        """Wait for task completion and return result.

        Args:
            timeout: Optional max seconds to wait — without it, a task row
                stuck in a non-terminal state would make this poll forever.

        Raises:
            asyncio.TimeoutError: When timeout elapses first.
        """
        task_id = await self.get_task_id()
        task = await self._service.get_task_by_id(task_id)

        if not task:
            raise RuntimeError(f"Task {task_id} not found")

        deadline = asyncio.get_event_loop().time() + timeout if timeout is not None else None

        # Poll until task reaches a terminal state ('stopped' included: it is
        # a deliberate terminal state, only ever restarted manually — waiting
        # past it would poll forever)
        while task.state not in [
            QueuedTaskState.done,
            QueuedTaskState.failed,
            QueuedTaskState.cancelled,
            QueuedTaskState.stopped,
        ]:
            if deadline is not None and asyncio.get_event_loop().time() >= deadline:
                raise asyncio.TimeoutError(f"Task {task_id} did not reach a terminal state within {timeout}s")
            await asyncio.sleep(0.5)
            task = await self._service.get_task_by_id(task_id)
            if not task:
                raise RuntimeError(f"Task {task_id} disappeared")

        if task.state == QueuedTaskState.done:
            return task.result if hasattr(task, "result") else None
        elif task.state == QueuedTaskState.failed:
            raise RuntimeError(f"Task failed: {task.exception_message}")
        elif task.state == QueuedTaskState.stopped:
            raise RuntimeError("Task was stopped")
        else:  # cancelled
            raise asyncio.CancelledError("Task was cancelled")

    async def get_state(self) -> QueuedTaskState:
        """Get current task state"""
        task_id = await self.get_task_id()
        task = await self._service.get_task_by_id(task_id)

        if not task:
            raise RuntimeError(f"Task {task_id} not found")

        return task.state

    async def _cancel_async(self) -> None:
        """Internal async cancel implementation"""
        try:
            task_id = await self.get_task_id()
            task = await self._service.get_task_by_id(task_id)

            if task and task.state in [QueuedTaskState.enqueued, QueuedTaskState.doing]:
                task.mark_as_cancelled()
                await task.save()
        except Exception:
            pass

    async def _stop_async(self) -> None:
        """Internal async stop implementation"""
        try:
            task_id = await self.get_task_id()
            task = await self._service.get_task_by_id(task_id)

            if task and task.state == QueuedTaskState.doing:
                task.mark_as_stopped()
                await task.save()
        except Exception:
            pass

    def _set_task_id(self, task_id: int) -> None:
        """Internal method to set task ID after creation"""
        self._task_id = task_id
        if self._creation_future and not self._creation_future.done():
            self._creation_future.set_result(task_id)

    def _set_creation_error(self, error: Exception) -> None:
        """Internal method to set creation error"""
        if self._creation_future and not self._creation_future.done():
            self._creation_future.set_exception(error)

    def __repr__(self) -> str:
        return f"QueuedTaskRef(id={self._task_id})"
