"""Runs the scheduled Discogs syncs: every 30 s it asks library_sync.tick whether one is due."""
import logging
import threading

from app.db import connect
from app.jobs.runner import JobRunner
from app.library_sync import tick

log = logging.getLogger(__name__)
INTERVAL = 30.0


class SyncScheduler:
    def __init__(self, runner: JobRunner, interval: float = INTERVAL):
        self._runner = runner
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="sync-schedule", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                conn = connect()
                try:
                    started = tick(conn, self._runner.enqueue)
                finally:
                    conn.close()
                if started:
                    log.info("scheduled sync", extra={"jobs": started})
            except Exception:  # a bad tick must never stop the schedule
                log.exception("scheduled sync failed")
