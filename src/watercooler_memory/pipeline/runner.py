"""Pipeline runner - orchestrates stage execution."""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from ulid import ULID

from .config import PipelineConfig
from .state import Stage, StageStatus, PipelineState, get_state_path, load_or_create_state
from .stages import get_runner, StageError
from .logging import PipelineLogger, format_duration
from .server_manager import ServerManager


class PipelineRunner:
    """Orchestrates pipeline execution with state management."""

    def __init__(
        self,
        config: PipelineConfig,
        run_id: Optional[str] = None,
        verbose: bool = False,
        auto_server: bool = True,
        stop_servers: bool = False,
        auto_approve: bool = False,
    ):
        self.config = config
        self.run_id = run_id or str(ULID()).lower()
        self.verbose = verbose
        self.auto_server = auto_server
        self.stop_servers_on_complete = stop_servers
        self.auto_approve = auto_approve

        # Ensure work directory exists
        config.ensure_work_dir()

        # Load or create state
        self.state = load_or_create_state(
            config.work_dir,
            self.run_id,
            config.threads_dir,
            config.test_mode,
        )

        # Initialize logger
        self.logger = PipelineLogger(
            self.run_id,
            config.work_dir,
            verbose=verbose,
        )

        # Initialize server manager
        self.server_manager = ServerManager(
            llm_api_base=config.llm.base_url,
            embedding_api_base=config.embedding.base_url,
            interactive=True,
            auto_approve=auto_approve,
            verbose=verbose,
        )

    def save_state(self) -> None:
        """Save current state to disk."""
        state_path = get_state_path(self.config.work_dir, self.run_id)
        self.state.save(state_path)

    def run_stage(self, stage: Stage, force: bool = False) -> bool:
        """Run a single stage.

        Args:
            stage: Stage to run
            force: Force re-run even if already completed

        Returns:
            True if stage completed successfully
        """
        stage_state = self.state.get_stage(stage)

        # Check if already completed
        if stage_state.status == StageStatus.COMPLETED and not force:
            self.logger.info(f"Stage '{stage.value}' already completed, skipping (use --force to re-run)")
            return True

        # Check dependencies
        can_run, reason = self.state.can_run_stage(stage)
        if not can_run and not force:
            self.logger.error(f"Cannot run stage '{stage.value}': {reason}")
            return False

        # Get runner
        runner = get_runner(stage, self.config, self.state, self.logger)

        # Validate inputs
        errors = runner.validate_inputs()
        if errors:
            for error in errors:
                self.logger.error(f"Validation error: {error}")
            stage_state.fail("Validation failed")
            self.save_state()
            return False

        # Run stage
        start_time = time.time()
        stage_state.start()
        self.save_state()

        self.logger.stage_start(stage)

        try:
            outputs = runner.run()
            stage_state.outputs = outputs
            stage_state.complete()
            elapsed = time.time() - start_time
            self.logger.stage_complete(stage)
            self.logger.info(f"Stage completed in {format_duration(elapsed)}")
            self.save_state()
            return True

        except StageError as e:
            stage_state.fail(str(e))
            self.logger.stage_failed(stage, str(e))
            self.save_state()
            return False

        except Exception as e:
            stage_state.fail(f"Unexpected error: {e}")
            self.logger.stage_failed(stage, str(e))
            self.logger.error(f"Traceback:", exc_info=True)
            self.save_state()
            return False

    def run_all(self, from_stage: Optional[Stage] = None, to_stage: Optional[Stage] = None) -> bool:
        """Run all stages in order.

        Args:
            from_stage: Start from this stage (skip earlier stages)
            to_stage: Stop after this stage

        Returns:
            True if all stages completed successfully
        """
        stages = Stage.ordered()

        # Filter stages
        if from_stage:
            try:
                idx = stages.index(from_stage)
                stages = stages[idx:]
            except ValueError:
                self.logger.error(f"Unknown stage: {from_stage}")
                return False

        if to_stage:
            try:
                idx = stages.index(to_stage)
                stages = stages[: idx + 1]
            except ValueError:
                self.logger.error(f"Unknown stage: {to_stage}")
                return False

        # Auto-start servers if enabled
        if self.auto_server:
            self.logger.info("Checking server availability...")
            if not self.server_manager.ensure_servers_running():
                self.logger.error("Required servers not available. Use --no-auto-server to skip this check.")
                return False

        self.logger.info(f"Running pipeline: {' → '.join(s.value for s in stages)}")
        if self.config.test_mode:
            self.logger.warning(f"Test mode enabled: limiting to {self.config.test_limit} documents")

        start_time = time.time()
        success = True

        try:
            for stage in stages:
                if not self.run_stage(stage):
                    success = False
                    break
        finally:
            # Stop servers if requested
            if self.stop_servers_on_complete:
                self.logger.info("Stopping servers...")
                self.server_manager.stop_servers()

        elapsed = time.time() - start_time

        # Log summary report
        self.logger.log_summary_report(elapsed)

        if success:
            self.logger.info(f"Pipeline completed successfully in {format_duration(elapsed)}")
        else:
            self.logger.error(f"Pipeline failed after {format_duration(elapsed)}")

        return success

    def status(self) -> dict:
        """Get current pipeline status."""
        stages_status = {}
        for stage in Stage.ordered():
            state = self.state.get_stage(stage)
            stages_status[stage.value] = {
                "status": state.status.value,
                "progress": f"{state.processed_items}/{state.total_items}" if state.total_items else "-",
                "started": state.started_at,
                "completed": state.completed_at,
                "error": state.error,
            }

        return {
            "run_id": self.run_id,
            "test_mode": self.state.test_mode,
            "threads_dir": self.state.threads_dir,
            "work_dir": self.state.work_dir,
            "is_complete": self.state.is_complete(),
            "current_stage": self.state.current_stage().value if self.state.current_stage() else None,
            "stages": stages_status,
        }

    def print_status(self) -> None:
        """Print formatted status to console."""
        status = self.status()

        print(f"\n{'=' * 60}")
        print(f"Pipeline Run: {status['run_id']}")
        print(f"{'=' * 60}")
        print(f"Threads: {status['threads_dir']}")
        print(f"Work Dir: {status['work_dir']}")
        print(f"Test Mode: {status['test_mode']}")
        print(f"Complete: {status['is_complete']}")
        if status["current_stage"]:
            print(f"Current Stage: {status['current_stage']}")
        print()

        for stage_name, stage_info in status["stages"].items():
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "skipped": "⏭️",
            }.get(stage_info["status"], "?")

            line = f"  {status_icon} {stage_name}: {stage_info['status']}"
            if stage_info["progress"] != "-":
                line += f" ({stage_info['progress']})"
            if stage_info["error"]:
                line += f" - {stage_info['error']}"
            print(line)

        print()


def create_runner(
    threads_dir: Path,
    work_dir: Optional[Path] = None,
    leanrag_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    test_mode: bool = False,
    verbose: bool = False,
    auto_server: bool = True,
    stop_servers: bool = False,
    auto_approve: bool = False,
) -> PipelineRunner:
    """Create a pipeline runner with configuration.

    Args:
        threads_dir: Path to threads directory
        work_dir: Work directory (default: ./pipeline_work)
        leanrag_dir: Path to LeanRAG repository
        run_id: Optional run ID (auto-generated if not provided)
        test_mode: Enable test mode with limited data
        verbose: Enable verbose logging
        auto_server: Automatically start LLM/embedding servers if not running
        stop_servers: Stop servers when pipeline completes
        auto_approve: Auto-approve prompts (model downloads, server starts)

    Returns:
        Configured PipelineRunner
    """
    from .config import load_config_from_env

    config = load_config_from_env(
        threads_dir=threads_dir,
        work_dir=work_dir,
        leanrag_dir=leanrag_dir,
        test_mode=test_mode,
    )

    return PipelineRunner(
        config,
        run_id=run_id,
        verbose=verbose,
        auto_server=auto_server,
        stop_servers=stop_servers,
        auto_approve=auto_approve,
    )
