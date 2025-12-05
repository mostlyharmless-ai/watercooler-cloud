"""Pipeline module for watercooler → LeanRAG processing.

This module provides tools for building and running the full pipeline:
  threads → export → extract → dedupe → build → query

Usage:
    from watercooler_memory.pipeline import create_runner, Stage

    # Create runner
    runner = create_runner(
        threads_dir=Path("/path/to/threads"),
        leanrag_dir=Path("/path/to/LeanRAG"),
        test_mode=True,  # Limited data for testing
    )

    # Run full pipeline
    runner.run_all()

    # Or run specific stage
    runner.run_stage(Stage.EXPORT)

    # Check status
    runner.print_status()

CLI:
    python -m watercooler_memory.pipeline --help
    python -m watercooler_memory.pipeline run --threads /path/to/threads --test
    python -m watercooler_memory.pipeline status --run-id abc123
"""

from .config import PipelineConfig, LLMConfig, EmbeddingConfig, load_config_from_env
from .state import Stage, StageStatus, PipelineState, StageState, list_runs
from .stages import StageRunner, StageError, get_runner
from .runner import PipelineRunner, create_runner
from .logging import PipelineLogger, format_duration

__all__ = [
    # Config
    "PipelineConfig",
    "LLMConfig",
    "EmbeddingConfig",
    "load_config_from_env",
    # State
    "Stage",
    "StageStatus",
    "PipelineState",
    "StageState",
    "list_runs",
    # Stages
    "StageRunner",
    "StageError",
    "get_runner",
    # Runner
    "PipelineRunner",
    "create_runner",
    # Logging
    "PipelineLogger",
    "format_duration",
]
