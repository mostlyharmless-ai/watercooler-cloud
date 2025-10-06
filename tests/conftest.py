from __future__ import annotations

import os
import sys
from pathlib import Path


def pytest_sessionstart(session):  # type: ignore[override]
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    # Ensure console scripts load in editable style as well
    os.environ.setdefault("PYTHONPATH", str(src))

