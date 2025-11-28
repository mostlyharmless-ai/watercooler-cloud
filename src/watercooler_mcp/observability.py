from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional


LOGGER_NAME = "watercooler_mcp"

# Environment variables for configuration
ENV_LOG_DIR = "WATERCOOLER_LOG_DIR"
ENV_LOG_LEVEL = "WATERCOOLER_LOG_LEVEL"
ENV_LOG_MAX_BYTES = "WATERCOOLER_LOG_MAX_BYTES"
ENV_LOG_BACKUP_COUNT = "WATERCOOLER_LOG_BACKUP_COUNT"
ENV_LOG_DISABLE_FILE = "WATERCOOLER_LOG_DISABLE_FILE"

# Defaults
DEFAULT_LOG_DIR = Path.home() / ".watercooler" / "logs"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5

_logger_initialized = False
_session_start = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")


def _get_log_level() -> int:
    """Get log level from environment, defaulting to INFO."""
    level_name = os.getenv(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL).upper()
    return getattr(logging, level_name, logging.INFO)


def _get_log_file_path() -> Optional[Path]:
    """Get the log file path, creating directories if needed.

    Returns None if file logging is disabled via WATERCOOLER_LOG_DISABLE_FILE=1.
    """
    if os.getenv(ENV_LOG_DISABLE_FILE, "").lower() in ("1", "true", "yes"):
        return None

    log_dir = Path(os.getenv(ENV_LOG_DIR, DEFAULT_LOG_DIR))
    log_dir.mkdir(parents=True, exist_ok=True)

    # Session-based filename: watercooler_2024-01-15_143022.log
    log_file = log_dir / f"watercooler_{_session_start}.log"
    return log_file


def _get_logger() -> logging.Logger:
    """Get or initialize the watercooler logger.

    By default, logs to ~/.watercooler/logs/watercooler_<session>.log

    Configuration via environment variables:
    - WATERCOOLER_LOG_DIR: Directory for log files (default: ~/.watercooler/logs/)
    - WATERCOOLER_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
    - WATERCOOLER_LOG_MAX_BYTES: Max log file size before rotation (default: 10MB)
    - WATERCOOLER_LOG_BACKUP_COUNT: Number of backup files to keep (default: 5)
    - WATERCOOLER_LOG_DISABLE_FILE: Set to 1 to disable file logging (stderr only)
    """
    global _logger_initialized
    logger = logging.getLogger(LOGGER_NAME)

    if not _logger_initialized:
        _logger_initialized = True
        logger.handlers.clear()  # Remove any existing handlers

        log_level = _get_log_level()
        logger.setLevel(log_level)

        # Human-readable formatter
        formatter = logging.Formatter(
            "[%(levelname)s %(asctime)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        )

        # File handler (enabled by default)
        log_file = _get_log_file_path()
        if log_file:
            max_bytes = int(os.getenv(ENV_LOG_MAX_BYTES, DEFAULT_MAX_BYTES))
            backup_count = int(os.getenv(ENV_LOG_BACKUP_COUNT, DEFAULT_BACKUP_COUNT))

            file_handler = RotatingFileHandler(
                str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(log_level)
            logger.addHandler(file_handler)

        # Also log to stderr for visibility (only warnings and above by default)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(max(log_level, logging.WARNING))
        logger.addHandler(stream_handler)

    return logger


def log_action(
    action: str,
    *,
    outcome: str = "ok",
    duration_ms: Optional[float] = None,
    tool_name: Optional[str] = None,
    input_chars: Optional[int] = None,
    output_chars: Optional[int] = None,
    **fields: Any,
) -> None:
    """Emit a structured log line for an action.

    Fields are serialized to JSON for safety. Keep schema lightweight.

    Args:
        action: Name of the action being logged
        outcome: Result status ("ok", "error", etc.)
        duration_ms: How long the action took in milliseconds
        tool_name: MCP tool name (for per-tool metrics)
        input_chars: Size of input in characters (for token estimation)
        output_chars: Size of output in characters (for token estimation)
        **fields: Additional fields to include
    """
    payload: Dict[str, Any] = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "outcome": outcome,
    }
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    if tool_name is not None:
        payload["tool"] = tool_name
    if input_chars is not None:
        payload["in_chars"] = input_chars
        payload["in_tokens_est"] = input_chars // 4  # Rough estimate
    if output_chars is not None:
        payload["out_chars"] = output_chars
        payload["out_tokens_est"] = output_chars // 4  # Rough estimate
    if fields:
        payload.update(fields)

    _get_logger().info(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def log_debug(message: str, **fields: Any) -> None:
    """Log a debug message with optional structured fields.

    Use this for detailed diagnostic output (replaces _diag()).
    Only emitted when log level is DEBUG.

    Args:
        message: Human-readable debug message
        **fields: Optional structured fields to append
    """
    logger = _get_logger()
    if logger.isEnabledFor(logging.DEBUG):
        if fields:
            field_str = " " + json.dumps(fields, separators=(",", ":"), sort_keys=True)
            logger.debug(f"{message}{field_str}")
        else:
            logger.debug(message)


def log_warning(message: str, **fields: Any) -> None:
    """Log a warning message with optional structured fields."""
    logger = _get_logger()
    if fields:
        field_str = " " + json.dumps(fields, separators=(",", ":"), sort_keys=True)
        logger.warning(f"{message}{field_str}")
    else:
        logger.warning(message)


def log_error(message: str, **fields: Any) -> None:
    """Log an error message with optional structured fields."""
    logger = _get_logger()
    if fields:
        field_str = " " + json.dumps(fields, separators=(",", ":"), sort_keys=True)
        logger.error(f"{message}{field_str}")
    else:
        logger.error(message)


@contextmanager
def timeit(
    action: str,
    *,
    tool_name: Optional[str] = None,
    input_chars: Optional[int] = None,
    **fields: Any,
):
    """Time a block and emit a structured log on exit.

    On exception, logs outcome="error" and re-raises.

    Args:
        action: Name of the action being timed
        tool_name: MCP tool name (for per-tool metrics)
        input_chars: Size of input in characters
        **fields: Additional fields to include

    Yields:
        A dict that can be updated with output_chars after the operation
    """
    start = time.perf_counter()
    result_info: Dict[str, Any] = {}
    try:
        yield result_info
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_action(
            action,
            outcome="ok",
            duration_ms=duration_ms,
            tool_name=tool_name,
            input_chars=input_chars,
            output_chars=result_info.get("output_chars"),
            **fields,
        )
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_action(
            action,
            outcome="error",
            duration_ms=duration_ms,
            tool_name=tool_name,
            input_chars=input_chars,
            **fields,
        )
        raise
