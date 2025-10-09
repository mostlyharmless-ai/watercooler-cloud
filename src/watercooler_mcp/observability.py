from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional


LOGGER_NAME = "watercooler_mcp"


def _get_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        # Default to INFO with a simple formatter if not configured by host app
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_action(action: str, *, outcome: str = "ok", duration_ms: Optional[int] = None, **fields: Any) -> None:
    """Emit a structured log line for an action.

    Fields are serialized to JSON for safety. Keep schema lightweight.
    """
    payload: Dict[str, Any] = {
        "action": action,
        "outcome": outcome,
    }
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    if fields:
        payload.update(fields)
    _get_logger().info(json.dumps(payload, separators=(",", ":"), sort_keys=True))


@contextmanager
def timeit(action: str, **fields: Any):
    """Time a block and emit a structured log on exit.

    On exception, logs outcome="error" and re-raises.
    """
    start = time.perf_counter()
    try:
        yield
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_action(action, outcome="ok", duration_ms=duration_ms, **fields)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_action(action, outcome="error", duration_ms=duration_ms, **fields)
        raise

