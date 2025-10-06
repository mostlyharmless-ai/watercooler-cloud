from __future__ import annotations

import os
import time
from pathlib import Path


class AdvisoryLock:
    """Simple file-based advisory lock with TTL and timeout.

    Environment variables (optional):
    - WCOOLER_LOCK_TTL: seconds to consider a lock stale
    - WCOOLER_LOCK_POLL: polling interval in seconds while waiting
    """

    def __init__(self, path: Path, *, ttl: int | None = None, timeout: int | None = None, force_break: bool = False):
        self.path = Path(path)
        self.ttl = ttl if ttl is not None else int(os.getenv("WCOOLER_LOCK_TTL", "30"))
        self.poll = float(os.getenv("WCOOLER_LOCK_POLL", "0.1"))
        self.timeout = timeout
        self.force_break = force_break
        self.acquired = False

    def _is_stale(self) -> bool:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        return (time.time() - mtime) > self.ttl

    def _write_pid(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(os.getpid()), encoding="utf-8")

    def _pid_of_lock(self) -> int | None:
        try:
            return int(self.path.read_text(encoding="utf-8").strip() or 0) or None
        except Exception:
            return None

    def acquire(self) -> bool:
        start = time.time()
        while True:
            try:
                # Create exclusively
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(str(os.getpid()))
                self.acquired = True
                return True
            except FileExistsError:
                # Allow immediate break if requested, even when timeout==0
                if self.force_break:
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                # If timeout is zero, do not wait
                if self.timeout == 0:
                    return False
                # When ttl<=0 treat as never stale
                if self.ttl > 0 and self._is_stale():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if self.timeout is not None and (time.time() - start) >= self.timeout:
                    return False
                time.sleep(self.poll)

    def release(self) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.acquired = False

    def __enter__(self):
        ok = self.acquire()
        if not ok:
            raise TimeoutError("Failed to acquire lock within timeout")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
