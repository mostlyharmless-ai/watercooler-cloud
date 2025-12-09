"""Configuration for baseline graph pipeline."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os


@dataclass
class LLMConfig:
    """LLM server configuration.

    Loaded via get_server_config("llm") with priority:
    1. Environment variables (LLM_API_BASE, LLM_MODEL, etc.)
    2. [servers.llm] in config.toml
    3. [memory_graph.llm] in config.toml (deprecated)
    4. Built-in defaults (Ollama on localhost:11434)
    """

    api_base: str = "http://localhost:11434/v1"
    model: str = "llama3.2:3b"
    api_key: str = "ollama"
    timeout: float = 120.0
    max_tokens: int = 256

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load from unified server configuration."""
        try:
            from watercooler.credentials import get_server_config
            config = get_server_config("llm")
        except ImportError:
            # Fallback if credentials module unavailable
            config = {}

        return cls(
            api_base=config.get("api_base", cls.api_base),
            model=config.get("model", cls.model),
            api_key=config.get("api_key", cls.api_key),
            timeout=config.get("timeout", cls.timeout),
            max_tokens=config.get("max_tokens", cls.max_tokens),
        )


@dataclass
class EmbeddingConfig:
    """Embedding server configuration.

    Loaded via get_server_config("embedding") with priority:
    1. Environment variables (EMBEDDING_API_BASE, EMBEDDING_MODEL, etc.)
    2. [servers.embedding] in config.toml
    3. [memory_graph.embedding] in config.toml (deprecated)
    4. Built-in defaults (llama.cpp on localhost:8080)
    """

    api_base: str = "http://localhost:8080/v1"
    model: str = "bge-m3"
    timeout: float = 60.0
    embedding_dim: int = 1024

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """Load from unified server configuration."""
        try:
            from watercooler.credentials import get_server_config
            config = get_server_config("embedding")
        except ImportError:
            # Fallback if credentials module unavailable
            config = {}

        return cls(
            api_base=config.get("api_base", cls.api_base),
            model=config.get("model", cls.model),
            timeout=config.get("timeout", cls.timeout),
        )


@dataclass
class PipelineConfig:
    """Full pipeline configuration."""

    threads_dir: Path = field(default_factory=lambda: Path("."))
    output_dir: Optional[Path] = None  # Default: {threads_dir}/graph/baseline

    # Processing limits
    test_limit: Optional[int] = None  # Limit threads processed
    skip_closed: bool = False
    fresh: bool = False  # Ignore cached results
    incremental: bool = False  # Only process changed threads

    # Services
    llm: LLMConfig = field(default_factory=LLMConfig.from_env)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig.from_env)

    # Feature flags
    extractive_only: bool = False  # Use extractive summarization (no LLM)
    skip_embeddings: bool = False  # Skip embedding generation

    def __post_init__(self):
        if self.output_dir is None:
            self.output_dir = self.threads_dir / "graph" / "baseline"

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of errors."""
        errors = []
        if not self.threads_dir.exists():
            errors.append(f"Threads directory not found: {self.threads_dir}")
        return errors
