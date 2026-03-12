"""Per-file lock management."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
import threading

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class FileLockManager:
    """Thread + process level lock manager for document operations."""

    def __init__(self) -> None:
        self._meta_lock = threading.Lock()
        self._thread_locks: dict[Path, threading.RLock] = defaultdict(threading.RLock)

    @contextmanager
    def acquire(self, path: Path):
        normalized = path.resolve()
        with self._meta_lock:
            thread_lock = self._thread_locks[normalized]

        with thread_lock:
            lock_path = normalized.with_suffix(normalized.suffix + ".lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)

            with lock_path.open("a+", encoding="utf-8") as lock_handle:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def acquire_many(self, paths: list[Path]):
        ordered = sorted({path.resolve() for path in paths})
        stack = []
        try:
            for path in ordered:
                ctx = self.acquire(path)
                ctx.__enter__()
                stack.append(ctx)
            yield
        finally:
            for ctx in reversed(stack):
                ctx.__exit__(None, None, None)
