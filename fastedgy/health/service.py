# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
import signal
import threading
import zlib

from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject

logger = logging.getLogger("fastedgy.health")


class Health:
    """Process-level readiness state and deploy-window detection.

    Each worker process owns its instance state (uvicorn forks per worker):
    readiness flips ON once the app lifespan completed its startup, and OFF
    as soon as a shutdown begins — the /health endpoint only reflects this
    state, so the orchestrator stops routing to a replica that is booting
    or draining.

    The deploy window is deterministic, no timer: the deployment
    orchestrator holds a session-level Postgres advisory lock (derived from
    ``settings.deploy_lock_name``) for the exact duration of a deploy, and a
    draining worker is in the window by definition.
    """

    def __init__(self, settings: BaseSettings = Inject(BaseSettings)):
        self._settings = settings
        self._ready = False
        self._shutting_down = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    @property
    def is_serving(self) -> bool:
        return self._ready and not self._shutting_down

    def mark_ready(self) -> None:
        self._ready = True

    def mark_shutting_down(self) -> None:
        self._shutting_down = True

    @property
    def deploy_lock_key(self) -> int | None:
        """Postgres advisory lock key derived from ``deploy_lock_name``.

        crc32 masked to a positive int32 so it fits the (classid=0, objid)
        form of single-argument advisory locks. None when no name is
        configured — the orchestrator-driven window is then disabled.
        """
        name = self._settings.deploy_lock_name
        if not name:
            return None
        return zlib.crc32(name.encode()) & 0x7FFFFFFF

    def install_graceful_shutdown(self) -> None:
        """Chain a SIGTERM handler that delays the real shutdown by
        ``shutdown_drain_seconds``: during the drain the worker keeps
        serving in-flight traffic while /health already answers 503, so the
        orchestrator stops sending new requests before the sockets close.
        """
        drain_seconds = self._settings.shutdown_drain_seconds

        if drain_seconds <= 0:
            return

        if threading.current_thread() is not threading.main_thread():
            return

        previous_handler = signal.getsignal(signal.SIGTERM)

        def _graceful_sigterm(signum, frame):
            if self._shutting_down:
                if callable(previous_handler):
                    previous_handler(signum, frame)
                return

            self.mark_shutting_down()
            logger.info("SIGTERM received, draining for %ss before shutdown", drain_seconds)

            def _trigger_real_shutdown() -> None:
                if callable(previous_handler):
                    previous_handler(signum, frame)

            timer = threading.Timer(drain_seconds, _trigger_real_shutdown)
            timer.daemon = True
            timer.start()

        signal.signal(signal.SIGTERM, _graceful_sigterm)

    async def in_deploy_window(self) -> bool:
        """True while a deploy is actually running: this worker drains after
        SIGTERM, or the orchestrator currently holds the deploy advisory
        lock. Deterministic on both ends — no timer.
        """
        if self._shutting_down:
            return True

        key = self.deploy_lock_key
        if key is None:
            return False

        from sqlalchemy import text

        from fastedgy.dependencies import get_service
        from fastedgy.orm import Database

        try:
            db = get_service(Database)
            row = await db.fetch_one(
                # The key is an internal constant, safely inlined (databasez's
                # fetch_one does not take separate values with a TextClause).
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_locks "
                    # objsubid = 1 restricts to the single-bigint advisory form
                    # the deploy orchestrator takes; classid holds its high 32
                    # bits, zero for a 31-bit crc key.
                    f"WHERE locktype = 'advisory' AND granted AND classid = 0 AND objid = {key} AND objsubid = 1"
                    ") AS held"
                )
            )
            return bool(row and row[0])
        except Exception as e:
            # The probe itself failing means the database cannot answer —
            # that is maintenance territory by definition.
            logger.warning(f"Deploy-window probe failed, assuming maintenance: {e!r}")
            return True


__all__ = [
    "Health",
]
