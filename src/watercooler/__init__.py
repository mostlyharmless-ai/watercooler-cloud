"""Watercooler: File-based collaboration for agentic coding."""

__version__ = "0.0.1"

from .lock import AdvisoryLock  # noqa: F401
from .fs import read, write, thread_path  # noqa: F401
from .header import bump_header  # noqa: F401

__all__ = [
    "AdvisoryLock",
    "read",
    "write",
    "thread_path",
    "bump_header",
    "__version__",
]

