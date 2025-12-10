"""Backend registry helpers."""

from __future__ import annotations

import os
import warnings
from typing import Callable

from . import BackendError, MemoryBackend
from .null import NullBackend

try:
    from .leanrag import LeanRAGBackend

    _LEANRAG_AVAILABLE = True
except ImportError:
    _LEANRAG_AVAILABLE = False

BackendFactory = Callable[[], MemoryBackend]

_REGISTRY: dict[str, BackendFactory] = {
    "null": lambda: NullBackend(),
}

# Register LeanRAG if available
if _LEANRAG_AVAILABLE:
    _REGISTRY["leanrag"] = lambda: LeanRAGBackend()


def register_backend(name: str, factory: BackendFactory) -> None:
    """Register a backend factory."""
    _REGISTRY[name] = factory


def get_backend(name: str) -> MemoryBackend:
    """Instantiate a backend by name."""
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise BackendError(f"Backend '{name}' is not registered") from exc
    return factory()


def list_backends() -> list[str]:
    """List registered backend names."""
    return sorted(_REGISTRY)


def resolve_backend(name: str | None = None) -> MemoryBackend:
    """Resolve backend by explicit name or WC_MEMORY_BACKEND env (default: null)."""
    backend_name = name or os.environ.get("WC_MEMORY_BACKEND", "null")
    return get_backend(backend_name)


def auto_register_builtin() -> None:
    """Attempt to register built-in adapters if available."""
    # LeanRAG (optional)
    if "leanrag" not in _REGISTRY:
        try:
            from .leanrag import LeanRAGBackend  # type: ignore

            register_backend("leanrag", lambda: LeanRAGBackend())
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Skipping LeanRAG backend registration: {exc}")

    # Graphiti (optional)
    if "graphiti" not in _REGISTRY:
        try:
            from .graphiti import GraphitiBackend  # type: ignore

            register_backend("graphiti", lambda: GraphitiBackend())
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Skipping Graphiti backend registration: {exc}")

