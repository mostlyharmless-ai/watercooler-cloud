"""Pipeline logging infrastructure."""

import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Generator, Any

from .state import Stage, StageStatus


@dataclass
class OperationTiming:
    """Timing data for a single operation."""

    name: str
    duration: float
    stage: Optional[str] = None
    details: dict = field(default_factory=dict)


@dataclass
class PipelineStats:
    """Accumulated statistics for a pipeline run."""

    # Timing
    total_duration: float = 0.0
    stage_durations: dict[str, float] = field(default_factory=dict)
    operation_timings: list[OperationTiming] = field(default_factory=list)

    # Counts
    threads_processed: int = 0
    entries_processed: int = 0
    documents_exported: int = 0
    chunks_created: int = 0
    entities_extracted: int = 0
    relations_extracted: int = 0
    entities_deduplicated: int = 0
    embeddings_generated: int = 0

    # Errors
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def record_timing(
        self, name: str, duration: float, stage: Optional[str] = None, **details: Any
    ) -> None:
        """Record timing for an operation."""
        self.operation_timings.append(
            OperationTiming(name=name, duration=duration, stage=stage, details=details)
        )

    def record_stage_duration(self, stage: str, duration: float) -> None:
        """Record duration for a stage."""
        self.stage_durations[stage] = duration

    def get_slowest_operations(self, n: int = 5) -> list[OperationTiming]:
        """Get the n slowest operations."""
        return sorted(self.operation_timings, key=lambda x: x.duration, reverse=True)[:n]

    def get_operation_summary(self, name: str) -> dict:
        """Get summary stats for operations with given name."""
        ops = [t for t in self.operation_timings if t.name == name]
        if not ops:
            return {"count": 0}
        durations = [t.duration for t in ops]
        return {
            "count": len(ops),
            "total": sum(durations),
            "avg": sum(durations) / len(durations),
            "min": min(durations),
            "max": max(durations),
        }


class PipelineFormatter(logging.Formatter):
    """Custom formatter for pipeline logs."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",
    }

    STAGE_COLORS = {
        "export": "\033[34m",  # Blue
        "extract": "\033[35m",  # Magenta
        "dedupe": "\033[36m",  # Cyan
        "build": "\033[33m",  # Yellow
    }

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        # Extract stage from record if present
        stage = getattr(record, "stage", None)
        run_id = getattr(record, "run_id", None)

        # Build timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        # Build prefix
        parts = [timestamp]
        if run_id:
            parts.append(f"[{run_id[:8]}]")
        if stage:
            stage_str = f"[{stage}]"
            if self.use_color:
                color = self.STAGE_COLORS.get(stage, "")
                stage_str = f"{color}{stage_str}{self.COLORS['RESET']}"
            parts.append(stage_str)

        prefix = " ".join(parts)

        # Build message with level color
        level = record.levelname
        msg = record.getMessage()

        if self.use_color:
            color = self.COLORS.get(level, "")
            if level == "INFO":
                # Don't colorize INFO messages, just the prefix
                formatted = f"{prefix} {msg}"
            else:
                formatted = f"{prefix} {color}{msg}{self.COLORS['RESET']}"
        else:
            formatted = f"{prefix} [{level}] {msg}"

        # Add exception info if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


class PipelineLogger:
    """Logger for pipeline runs with file and console output."""

    def __init__(
        self,
        run_id: str,
        work_dir: Path,
        stage: Optional[Stage] = None,
        verbose: bool = False,
        stats: Optional[PipelineStats] = None,
    ):
        self.run_id = run_id
        self.work_dir = work_dir
        self.stage = stage
        self.verbose = verbose
        self.stats = stats or PipelineStats()
        self._stage_start_time: Optional[float] = None

        # Set up logger
        self.logger = logging.getLogger(f"pipeline.{run_id}")
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.logger.handlers.clear()

        # Console handler (colored)
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG if verbose else logging.INFO)
        console.setFormatter(PipelineFormatter(use_color=sys.stdout.isatty()))
        self.logger.addHandler(console)

        # File handler (plain text)
        log_dir = work_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Main log file for the run
        file_handler = logging.FileHandler(log_dir / f"{run_id}.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(PipelineFormatter(use_color=False))
        self.logger.addHandler(file_handler)

        # Stage-specific log file if stage is set
        if stage:
            stage_handler = logging.FileHandler(log_dir / f"{run_id}.{stage.value}.log")
            stage_handler.setLevel(logging.DEBUG)
            stage_handler.setFormatter(PipelineFormatter(use_color=False))
            self.logger.addHandler(stage_handler)

    def _log(self, level: int, msg: str, *args, **kwargs) -> None:
        """Log with extra context."""
        extra = {"run_id": self.run_id, "stage": self.stage.value if self.stage else None}
        self.logger.log(level, msg, *args, extra=extra, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def stage_start(self, stage: Stage, total_items: int = 0) -> None:
        """Log stage start."""
        self.stage = stage
        self._stage_start_time = time.time()
        if total_items:
            self.info(f"Starting stage: {stage.value} ({total_items} items)")
        else:
            self.info(f"Starting stage: {stage.value}")

    def stage_complete(self, stage: Stage, processed: int = 0, failed: int = 0) -> None:
        """Log stage completion."""
        duration = 0.0
        if self._stage_start_time:
            duration = time.time() - self._stage_start_time
            self.stats.record_stage_duration(stage.value, duration)
            self._stage_start_time = None

        if failed:
            self.warning(f"Completed stage: {stage.value} ({processed} processed, {failed} failed) in {format_duration(duration)}")
        else:
            self.info(f"Completed stage: {stage.value} ({processed} processed) in {format_duration(duration)}")
        self.stage = None

    def stage_failed(self, stage: Stage, error: str) -> None:
        """Log stage failure."""
        self.stats.errors.append(f"{stage.value}: {error}")
        self.error(f"Stage failed: {stage.value} - {error}")
        self.stage = None

    @contextmanager
    def timed(self, operation: str, log_start: bool = True, **details: Any) -> Generator[None, None, None]:
        """Context manager for timing operations.

        Args:
            operation: Name of the operation being timed
            log_start: Whether to log when operation starts
            **details: Additional details to record with timing

        Usage:
            with logger.timed("llm_call", doc_id="123"):
                result = call_llm(prompt)
        """
        if log_start:
            self.debug(f"Starting: {operation}")
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            stage_name = self.stage.value if self.stage else None
            self.stats.record_timing(operation, duration, stage=stage_name, **details)
            self.debug(f"Completed: {operation} in {format_duration(duration)}")

    def record_stat(self, name: str, value: int = 1, increment: bool = True) -> None:
        """Record a statistic.

        Args:
            name: Stat name (must match PipelineStats attribute)
            value: Value to set or increment by
            increment: If True, add to existing; if False, set value
        """
        if hasattr(self.stats, name):
            if increment:
                setattr(self.stats, name, getattr(self.stats, name) + value)
            else:
                setattr(self.stats, name, value)
        else:
            self.warning(f"Unknown stat: {name}")

    def progress(self, current: int, total: int, message: str = "") -> None:
        """Log progress update."""
        pct = (current / total * 100) if total > 0 else 0
        if message:
            self.info(f"[{current}/{total}] ({pct:.1f}%) {message}")
        else:
            self.info(f"[{current}/{total}] ({pct:.1f}%)")

    def batch_start(self, batch_num: int, total_batches: int, batch_size: int) -> None:
        """Log batch start."""
        self.debug(f"Starting batch {batch_num}/{total_batches} ({batch_size} items)")

    def batch_complete(self, batch_num: int, total_batches: int, processed: int, failed: int = 0) -> None:
        """Log batch completion."""
        if failed:
            self.info(f"Batch {batch_num}/{total_batches}: {processed} processed, {failed} failed")
        else:
            self.debug(f"Batch {batch_num}/{total_batches}: {processed} processed")

    def log_summary_report(self, total_duration: float) -> None:
        """Log a summary report of the pipeline run.

        Args:
            total_duration: Total pipeline duration in seconds
        """
        self.stats.total_duration = total_duration

        # Build report
        lines = [
            "",
            "=" * 60,
            "PIPELINE SUMMARY REPORT",
            "=" * 60,
            "",
            f"Run ID: {self.run_id}",
            f"Total Duration: {format_duration(total_duration)}",
            "",
            "STAGE TIMINGS:",
            "-" * 40,
        ]

        for stage, duration in self.stats.stage_durations.items():
            pct = (duration / total_duration * 100) if total_duration > 0 else 0
            lines.append(f"  {stage:12} {format_duration(duration):>10}  ({pct:5.1f}%)")

        lines.extend([
            "",
            "PROCESSING STATS:",
            "-" * 40,
            f"  Threads processed:      {self.stats.threads_processed:>8}",
            f"  Entries processed:      {self.stats.entries_processed:>8}",
            f"  Documents exported:     {self.stats.documents_exported:>8}",
            f"  Chunks created:         {self.stats.chunks_created:>8}",
            f"  Entities extracted:     {self.stats.entities_extracted:>8}",
            f"  Relations extracted:    {self.stats.relations_extracted:>8}",
            f"  Entities deduplicated:  {self.stats.entities_deduplicated:>8}",
            f"  Embeddings generated:   {self.stats.embeddings_generated:>8}",
        ])

        # Slowest operations
        slowest = self.stats.get_slowest_operations(5)
        if slowest:
            lines.extend([
                "",
                "SLOWEST OPERATIONS:",
                "-" * 40,
            ])
            for op in slowest:
                stage_str = f"[{op.stage}]" if op.stage else ""
                lines.append(f"  {format_duration(op.duration):>10}  {op.name} {stage_str}")

        # Operation summaries for common operations
        for op_name in ["llm_call", "embedding_call", "file_read", "file_write"]:
            summary = self.stats.get_operation_summary(op_name)
            if summary["count"] > 0:
                lines.extend([
                    "",
                    f"{op_name.upper()} SUMMARY:",
                    "-" * 40,
                    f"  Count: {summary['count']}",
                    f"  Total: {format_duration(summary['total'])}",
                    f"  Avg:   {format_duration(summary['avg'])}",
                    f"  Min:   {format_duration(summary['min'])}",
                    f"  Max:   {format_duration(summary['max'])}",
                ])

        # Errors and warnings
        if self.stats.errors:
            lines.extend([
                "",
                "ERRORS:",
                "-" * 40,
            ])
            for err in self.stats.errors:
                lines.append(f"  ❌ {err}")

        if self.stats.warnings:
            lines.extend([
                "",
                "WARNINGS:",
                "-" * 40,
            ])
            for warn in self.stats.warnings:
                lines.append(f"  ⚠️  {warn}")

        lines.extend([
            "",
            "=" * 60,
            "",
        ])

        # Log each line
        for line in lines:
            self.info(line)


def create_progress_callback(logger: PipelineLogger) -> Callable[[int, int, str], None]:
    """Create a progress callback function for use with build operations."""

    def callback(current: int, total: int, message: str) -> None:
        logger.progress(current, total, message)

    return callback


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
