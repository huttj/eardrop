from __future__ import annotations

import logging
import threading
from pathlib import Path
from queue import Empty, Queue

from .config import Config
from .database import Database
from .pipeline import process_recording

log = logging.getLogger(__name__)


class Worker:
    """Background worker that processes audio files from a queue."""

    def __init__(self, config: Config, db: Database, queue: Queue[Path]) -> None:
        self.config = config
        self.db = db
        self.queue = queue
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Worker started")

    def _run(self) -> None:
        while self._running:
            try:
                path = self.queue.get(timeout=1.0)
            except Empty:
                continue

            try:
                process_recording(path, self.config, self.db)
            except Exception:
                log.exception("Worker failed to process %s", path)
            finally:
                self.queue.task_done()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        log.info("Worker stopped")
