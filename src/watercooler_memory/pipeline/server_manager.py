"""Server lifecycle management for pipeline.

Auto-starts LLM and embedding servers when pipeline runs,
downloading models if needed with user approval.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


# Default ports (match local_server.py and embedding_server.py)
DEFAULT_LLM_PORT = 8000
DEFAULT_EMBEDDING_PORT = 8080
DEFAULT_HOST = "127.0.0.1"

# Health check settings
HEALTH_CHECK_TIMEOUT = 5.0
HEALTH_CHECK_RETRIES = 30
HEALTH_CHECK_INTERVAL = 1.0


@dataclass
class ServerConfig:
    """Configuration for a server endpoint."""

    name: str
    api_base: str
    default_port: int
    module: str  # Python module to run (e.g., "watercooler_memory.local_server")

    @property
    def host(self) -> str:
        """Extract host from api_base."""
        parsed = urlparse(self.api_base)
        return parsed.hostname or DEFAULT_HOST

    @property
    def port(self) -> int:
        """Extract port from api_base."""
        parsed = urlparse(self.api_base)
        return parsed.port or self.default_port

    @property
    def health_url(self) -> str:
        """URL to check server health."""
        return f"{self.api_base.rstrip('/')}/models"


@dataclass
class ServerManager:
    """Manages LLM and embedding server lifecycle.

    Automatically starts servers if not running, downloads models
    if needed, and optionally stops servers when done.
    """

    llm_api_base: str = f"http://{DEFAULT_HOST}:{DEFAULT_LLM_PORT}/v1"
    embedding_api_base: str = f"http://{DEFAULT_HOST}:{DEFAULT_EMBEDDING_PORT}/v1"
    interactive: bool = True
    auto_approve: bool = False
    verbose: bool = False

    _llm_process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _embedding_process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _servers_we_started: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        """Register cleanup on exit."""
        atexit.register(self._cleanup)

    @property
    def llm_config(self) -> ServerConfig:
        """LLM server configuration."""
        return ServerConfig(
            name="LLM",
            api_base=self.llm_api_base,
            default_port=DEFAULT_LLM_PORT,
            module="watercooler_memory.local_server",
        )

    @property
    def embedding_config(self) -> ServerConfig:
        """Embedding server configuration."""
        return ServerConfig(
            name="Embedding",
            api_base=self.embedding_api_base,
            default_port=DEFAULT_EMBEDDING_PORT,
            module="watercooler_memory.embedding_server",
        )

    def check_server(self, config: ServerConfig) -> bool:
        """Check if a server is running and healthy.

        Args:
            config: Server configuration to check.

        Returns:
            True if server responds to health check.
        """
        try:
            response = requests.get(
                config.health_url,
                timeout=HEALTH_CHECK_TIMEOUT,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def check_llm_server(self) -> bool:
        """Check if LLM server is running."""
        return self.check_server(self.llm_config)

    def check_embedding_server(self) -> bool:
        """Check if embedding server is running."""
        return self.check_server(self.embedding_config)

    def _prompt_user(self, message: str, default: bool = True) -> bool:
        """Prompt user for confirmation.

        Args:
            message: Question to ask.
            default: Default answer if user presses Enter.

        Returns:
            User's choice.
        """
        if self.auto_approve:
            return True

        if not self.interactive:
            return default

        suffix = " [Y/n] " if default else " [y/N] "
        try:
            response = input(message + suffix).strip().lower()
            if not response:
                return default
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            print()
            return False

    def _start_server_process(
        self,
        config: ServerConfig,
        extra_args: Optional[list[str]] = None,
    ) -> Optional[subprocess.Popen]:
        """Start a server as a subprocess.

        Args:
            config: Server configuration.
            extra_args: Additional command line arguments.

        Returns:
            Subprocess handle, or None if failed.
        """
        cmd = [
            sys.executable,
            "-m",
            config.module,
            "--host",
            config.host,
            "--port",
            str(config.port),
        ]

        if extra_args:
            cmd.extend(extra_args)

        if self.verbose:
            logger.info(f"Starting {config.name} server: {' '.join(cmd)}")

        try:
            # Start server with output suppressed unless verbose
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE if not self.verbose else None,
                stderr=subprocess.PIPE if not self.verbose else None,
                # Don't propagate signals to subprocess
                preexec_fn=os.setpgrp if hasattr(os, "setpgrp") else None,
            )
            return process
        except Exception as e:
            logger.error(f"Failed to start {config.name} server: {e}")
            return None

    def _wait_for_server(self, config: ServerConfig) -> bool:
        """Wait for server to become healthy.

        Args:
            config: Server configuration.

        Returns:
            True if server is healthy within timeout.
        """
        for i in range(HEALTH_CHECK_RETRIES):
            if self.check_server(config):
                if self.verbose:
                    logger.info(f"{config.name} server is ready")
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
            if self.verbose and i % 5 == 4:
                logger.info(f"Waiting for {config.name} server... ({i + 1}s)")

        return False

    def start_llm_server(self) -> bool:
        """Start LLM server if not running.

        Returns:
            True if server is running (was running or started successfully).
        """
        config = self.llm_config

        # Check if already running
        if self.check_server(config):
            if self.verbose:
                logger.info(f"{config.name} server already running at {config.api_base}")
            return True

        # Prompt user
        if not self._prompt_user(
            f"\n{config.name} server not running at {config.api_base}\n"
            f"Start local LLM server?"
        ):
            logger.warning(f"{config.name} server not started (user declined)")
            return False

        print(f"Starting {config.name} server...")
        print("(First run may download model ~2GB)")

        # Start server process
        self._llm_process = self._start_server_process(config)
        if not self._llm_process:
            return False

        self._servers_we_started.append("llm")

        # Wait for server to be ready
        if not self._wait_for_server(config):
            logger.error(f"{config.name} server failed to start within timeout")
            self._stop_process(self._llm_process)
            self._llm_process = None
            return False

        print(f"{config.name} server started at {config.api_base}")
        return True

    def start_embedding_server(self) -> bool:
        """Start embedding server if not running.

        Returns:
            True if server is running (was running or started successfully).
        """
        config = self.embedding_config

        # Check if already running
        if self.check_server(config):
            if self.verbose:
                logger.info(f"{config.name} server already running at {config.api_base}")
            return True

        # Prompt user
        if not self._prompt_user(
            f"\n{config.name} server not running at {config.api_base}\n"
            f"Start local embedding server?"
        ):
            logger.warning(f"{config.name} server not started (user declined)")
            return False

        print(f"Starting {config.name} server...")
        print("(First run may download model ~2GB)")

        # Start server process
        self._embedding_process = self._start_server_process(config)
        if not self._embedding_process:
            return False

        self._servers_we_started.append("embedding")

        # Wait for server to be ready
        if not self._wait_for_server(config):
            logger.error(f"{config.name} server failed to start within timeout")
            self._stop_process(self._embedding_process)
            self._embedding_process = None
            return False

        print(f"{config.name} server started at {config.api_base}")
        return True

    def ensure_servers_running(self) -> bool:
        """Ensure both LLM and embedding servers are running.

        Starts servers if needed, with user prompts for approval.

        Returns:
            True if both servers are running.
        """
        llm_ok = self.start_llm_server()
        embedding_ok = self.start_embedding_server()

        if llm_ok and embedding_ok:
            return True

        # Report what's missing
        missing = []
        if not llm_ok:
            missing.append("LLM")
        if not embedding_ok:
            missing.append("Embedding")

        logger.error(f"Required servers not available: {', '.join(missing)}")
        return False

    def _stop_process(self, process: Optional[subprocess.Popen]) -> None:
        """Stop a subprocess gracefully.

        Args:
            process: Subprocess to stop.
        """
        if process is None:
            return

        try:
            # Try graceful shutdown first
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                process.kill()
                process.wait()
        except Exception as e:
            logger.warning(f"Error stopping server process: {e}")

    def stop_servers(self) -> None:
        """Stop any servers we started."""
        if "llm" in self._servers_we_started:
            if self.verbose:
                logger.info("Stopping LLM server...")
            self._stop_process(self._llm_process)
            self._llm_process = None

        if "embedding" in self._servers_we_started:
            if self.verbose:
                logger.info("Stopping embedding server...")
            self._stop_process(self._embedding_process)
            self._embedding_process = None

        self._servers_we_started.clear()

    def _cleanup(self) -> None:
        """Cleanup handler called on exit."""
        # Only stop servers we started
        if self._servers_we_started:
            logger.debug("Cleaning up started servers...")
            self.stop_servers()

    def status(self) -> dict[str, bool]:
        """Get status of both servers.

        Returns:
            Dict with 'llm' and 'embedding' keys indicating if each is running.
        """
        return {
            "llm": self.check_llm_server(),
            "embedding": self.check_embedding_server(),
        }

    def print_status(self) -> None:
        """Print server status to stdout."""
        status = self.status()
        print("\nServer Status:")
        print(f"  LLM ({self.llm_api_base}): {'running' if status['llm'] else 'not running'}")
        print(f"  Embedding ({self.embedding_api_base}): {'running' if status['embedding'] else 'not running'}")

        if self._servers_we_started:
            print(f"\n  Servers started by this session: {', '.join(self._servers_we_started)}")
