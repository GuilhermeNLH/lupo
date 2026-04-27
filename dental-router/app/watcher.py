"""Watchdog-based directory monitor with debounce."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.logger import logger
from app.models import DetectedItem


class _Handler(FileSystemEventHandler):
    def __init__(
        self,
        callback: Callable[[DetectedItem], None],
        debounce: float,
    ) -> None:
        super().__init__()
        self._callback = callback
        self._debounce = debounce
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        self._timers: dict[str, threading.Timer] = {}

    # ------------------------------------------------------------------ #
    def _fire(self, path: str, item_type: str) -> None:
        """Called once the debounce timer fires – delivers the item."""
        with self._lock:
            self._timers.pop(path, None)
            if path in self._seen:
                return
            self._seen.add(path)

        p = Path(path)
        item = DetectedItem.new(p.name, path, item_type)  # type: ignore[arg-type]
        try:
            self._callback(item)
        except Exception as exc:
            logger.error(f"Callback error for {path!r}: {exc}")

    def _schedule(self, path: str, item_type: str) -> None:
        """(Re-)schedule a debounced delivery for *path*."""
        with self._lock:
            existing = self._timers.pop(path, None)
            if existing is not None:
                existing.cancel()
            t = threading.Timer(self._debounce, self._fire, args=(path, item_type))
            self._timers[path] = t
            t.start()

    # ------------------------------------------------------------------ #
    def on_created(self, event: FileSystemEvent) -> None:
        item_type = "folder" if event.is_directory else "file"
        self._schedule(str(event.src_path), item_type)

    def reset_seen(self) -> None:
        """Clear the set of already-seen paths (allows re-detection)."""
        with self._lock:
            self._seen.clear()


class Watcher:
    """Monitors a single directory for new files and folders."""

    def __init__(
        self,
        source_dir: str,
        callback: Callable[[DetectedItem], None],
        debounce: float = 2.0,
    ) -> None:
        self._source_dir = source_dir
        self._callback = callback
        self._debounce = debounce
        self._observer: Optional[Observer] = None
        self._handler: Optional[_Handler] = None
        self._running = False

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self._running:
            return

        self._handler = _Handler(self._callback, self._debounce)
        self._observer = Observer()
        self._observer.schedule(self._handler, self._source_dir, recursive=False)
        self._observer.start()
        self._running = True
        logger.info(f"Watcher started on: {self._source_dir}")

    def stop(self) -> None:
        if not self._running or self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._running = False
        logger.info("Watcher stopped.")

    @property
    def is_running(self) -> bool:
        return self._running
