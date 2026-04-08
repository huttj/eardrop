from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import Config

log = logging.getLogger(__name__)


class AudioFileHandler(FileSystemEventHandler):
    """Watches for new audio files, handles iCloud placeholders and debouncing."""

    def __init__(self, config: Config, queue: Queue[Path]) -> None:
        self.config = config
        self.queue = queue
        self._pending: dict[str, float] = {}  # path -> last_event_time
        self._lock = threading.Lock()

        # Start debounce checker thread
        self._running = True
        self._checker = threading.Thread(target=self._debounce_loop, daemon=True)
        self._checker.start()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle_file(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle_file(Path(event.src_path))

    def _handle_file(self, path: Path) -> None:
        # Handle iCloud placeholder files (.filename.ext.icloud)
        if path.name.startswith(".") and path.suffix == ".icloud":
            self._trigger_icloud_download(path)
            return

        if path.suffix.lower() not in self.config.audio_extensions:
            return

        with self._lock:
            self._pending[str(path)] = time.time()

    def _trigger_icloud_download(self, placeholder: Path) -> None:
        """Request iCloud to download a placeholder file."""
        # The real filename is: remove leading "." and trailing ".icloud"
        real_name = placeholder.name[1:]  # remove leading dot
        if real_name.endswith(".icloud"):
            real_name = real_name[:-7]  # remove ".icloud" suffix

        real_path = placeholder.parent / real_name
        if real_path.suffix.lower() not in self.config.audio_extensions:
            return

        log.info("Triggering iCloud download for %s", real_name)
        try:
            subprocess.run(["brctl", "download", str(placeholder.parent / real_name)],
                           capture_output=True, timeout=10)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            log.warning("brctl download failed for %s", real_name)

    def _debounce_loop(self) -> None:
        """Check pending files and enqueue them after debounce period."""
        while self._running:
            time.sleep(1.0)
            now = time.time()
            ready: list[str] = []

            with self._lock:
                for path_str, last_time in list(self._pending.items()):
                    if now - last_time >= self.config.debounce_seconds:
                        ready.append(path_str)

                for path_str in ready:
                    del self._pending[path_str]

            for path_str in ready:
                path = Path(path_str)
                if path.exists() and path.stat().st_size > 0:
                    log.info("Enqueuing %s for processing", path.name)
                    self.queue.put(path)

    def stop(self) -> None:
        self._running = False


class Watcher:
    """Watches the inbox directory for new audio files."""

    def __init__(self, config: Config, queue: Queue[Path]) -> None:
        self.config = config
        self.queue = queue
        self.handler = AudioFileHandler(config, queue)
        self.observer = Observer()
        self._scan_timer: threading.Timer | None = None

    def start(self) -> None:
        self.config.watch_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self.handler, str(self.config.watch_dir), recursive=False)
        self.observer.start()
        log.info("Watching %s for audio files", self.config.watch_dir)

        # Periodic scan to catch files missed during iCloud sync
        self._schedule_scan()

    def _schedule_scan(self) -> None:
        self._scan_timer = threading.Timer(
            self.config.scan_interval_seconds, self._periodic_scan
        )
        self._scan_timer.daemon = True
        self._scan_timer.start()

    def _periodic_scan(self) -> None:
        """Scan directory for any unprocessed files."""
        try:
            for path in self.config.watch_dir.iterdir():
                if path.suffix.lower() in self.config.audio_extensions:
                    self.handler._handle_file(path)
                elif path.name.startswith(".") and path.suffix == ".icloud":
                    self.handler._trigger_icloud_download(path)
        except Exception:
            log.exception("Periodic scan failed")
        finally:
            self._schedule_scan()

    def stop(self) -> None:
        self.handler.stop()
        self.observer.stop()
        self.observer.join(timeout=5)
        if self._scan_timer:
            self._scan_timer.cancel()
        log.info("Watcher stopped")
