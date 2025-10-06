from __future__ import annotations

import os
from pathlib import Path


def resolve_threads_dir(cli_value: str | None = None) -> Path:
    """Resolve threads directory using precedence: CLI > env > default.

    Env var: WATERCOOLER_DIR
    Default: ./watercooler
    """
    if cli_value:
        return Path(cli_value)
    env = os.getenv("WATERCOOLER_DIR")
    if env:
        return Path(env)
    return Path("watercooler")

