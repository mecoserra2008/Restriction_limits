"""Tiny TTL+mtime cache for Excel snapshots so we do not re-parse on every request."""
from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional, Tuple

from ..config import SETTINGS


class FileCache:
    def __init__(self, ttl: int = SETTINGS.cache_ttl_seconds) -> None:
        self.ttl = ttl
        self._lock = Lock()
        self._store: dict[str, Tuple[float, float, Any]] = {}

    def get_or_load(self, path: Path, loader: Callable[[Path], Any]) -> Any:
        key = str(path)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = -1.0
        now = time.time()
        with self._lock:
            cached = self._store.get(key)
            if cached:
                stored_mtime, stored_at, value = cached
                if stored_mtime == mtime and (now - stored_at) < self.ttl:
                    return value
        value = loader(path)
        with self._lock:
            self._store[key] = (mtime, now, value)
        return value

    def invalidate(self, path: Optional[Path] = None) -> None:
        with self._lock:
            if path is None:
                self._store.clear()
            else:
                self._store.pop(str(path), None)


CACHE = FileCache()
