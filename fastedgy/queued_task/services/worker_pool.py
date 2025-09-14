# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

import uuid

import logging

from typing import Dict, Optional, List

from fastedgy.dependencies import get_service
from fastedgy.queued_task.config import QueuedTaskConfig
from fastedgy.queued_task.services.queue_worker import QueueWorker


logger = logging.getLogger("queued_task.worker_pool")


class WorkerPool:
    """Manages a pool of queue workers with intelligent timeout handling"""

    def __init__(self, max_workers: Optional[int] = None):
        self.config = get_service(QueuedTaskConfig)
        self.max_workers = max_workers or self.config.max_workers
        self.idle_workers: asyncio.Queue[QueueWorker] = asyncio.Queue()
        self.busy_workers: Dict[str, QueueWorker] = {}
        self.worker_timeout_tasks: Dict[str, asyncio.Task] = {}

        logger.info(f"WorkerPool initialized with max_workers={self.max_workers}")

    async def get_available_worker(self) -> Optional[QueueWorker]:
        """
        Get an available worker from the pool

        Returns:
            QueueWorker if available or can be created, None if pool is full
        """
        # Try to get an idle worker first
        if not self.idle_workers.empty():
            worker = await self.idle_workers.get()

            # Cancel its timeout task
            if worker.worker_id in self.worker_timeout_tasks:
                self.worker_timeout_tasks[worker.worker_id].cancel()
                del self.worker_timeout_tasks[worker.worker_id]

            # Move to busy workers
            self.busy_workers[worker.worker_id] = worker
            logger.debug(f"Reusing idle worker {worker.worker_id}")
            return worker

        # Create new worker if under max limit
        total_workers = len(self.busy_workers) + self.idle_workers.qsize()
        if total_workers < self.max_workers:
            worker_id = f"worker_{uuid.uuid4().hex[:8]}"
            worker = QueueWorker(worker_id)
            self.busy_workers[worker_id] = worker
            logger.info(
                f"Created new worker {worker_id} (total: {total_workers + 1}/{self.max_workers})"
            )
            return worker

        # Pool is full
        logger.warning(
            f"Worker pool is full ({self.max_workers} workers), task will wait"
        )
        return None

    async def return_worker(self, worker: QueueWorker) -> None:
        """
        Return a worker to the idle pool with timeout management

        Args:
            worker: The worker to return to the pool
        """
        # Remove from busy workers
        if worker.worker_id in self.busy_workers:
            del self.busy_workers[worker.worker_id]

        # Add to idle workers
        await self.idle_workers.put(worker)

        # Start idle timeout task
        timeout_task = asyncio.create_task(self._worker_idle_timeout(worker))
        self.worker_timeout_tasks[worker.worker_id] = timeout_task

        logger.debug(
            f"Worker {worker.worker_id} returned to idle pool (timeout in {self.config.worker_idle_timeout}s)"
        )

    async def _worker_idle_timeout(self, worker: QueueWorker) -> None:
        """
        Handle worker idle timeout - remove worker after configured idle time

        Args:
            worker: The worker to monitor for timeout
        """
        try:
            await asyncio.sleep(self.config.worker_idle_timeout)

            # Check if worker is still idle and remove it
            if worker.worker_id in self.worker_timeout_tasks:
                # Try to remove from idle queue (it might have been picked up)
                try:
                    # Create a new queue without this worker
                    new_queue = asyncio.Queue()
                    while not self.idle_workers.empty():
                        idle_worker = await self.idle_workers.get()
                        if idle_worker.worker_id != worker.worker_id:
                            await new_queue.put(idle_worker)

                    self.idle_workers = new_queue

                    logger.info(
                        f"Worker {worker.worker_id} removed due to idle timeout"
                    )

                except Exception as e:
                    logger.error(f"Error removing idle worker {worker.worker_id}: {e}")

                # Clean up timeout task
                del self.worker_timeout_tasks[worker.worker_id]

        except asyncio.CancelledError:
            # Timeout was cancelled (worker was reused)
            logger.debug(f"Idle timeout cancelled for worker {worker.worker_id}")

    async def get_pool_stats(self) -> Dict[str, int]:
        """Get current pool statistics"""
        return {
            "max_workers": self.max_workers,
            "busy_workers": len(self.busy_workers),
            "idle_workers": self.idle_workers.qsize(),
            "total_workers": len(self.busy_workers) + self.idle_workers.qsize(),
            "pending_timeouts": len(self.worker_timeout_tasks),
        }

    async def shutdown(self) -> None:
        """Shutdown the worker pool and cancel all pending tasks"""
        logger.info("Shutting down worker pool...")

        # Cancel all timeout tasks
        for task in self.worker_timeout_tasks.values():
            task.cancel()

        # Wait for timeout tasks to complete
        if self.worker_timeout_tasks:
            await asyncio.gather(
                *self.worker_timeout_tasks.values(), return_exceptions=True
            )

        self.worker_timeout_tasks.clear()
        self.busy_workers.clear()

        # Clear idle workers
        while not self.idle_workers.empty():
            await self.idle_workers.get()

        logger.info("Worker pool shutdown complete")

    def get_busy_workers(self) -> List[QueueWorker]:
        """Get list of currently busy workers"""
        return list(self.busy_workers.values())

    def __str__(self):
        stats = asyncio.create_task(self.get_pool_stats())
        return f"WorkerPool(max={self.max_workers}, busy={len(self.busy_workers)}, idle={self.idle_workers.qsize()})"
