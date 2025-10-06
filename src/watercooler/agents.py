from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from typing import Tuple


def _load_agents_registry(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _split_agent_and_tag(agent: str) -> Tuple[str, str | None]:
    if "#" in agent:
        a, tag = agent.split("#", 1)
        return a, tag or None
    return agent, None


def _get_git_user() -> str | None:
    # Fallback to OS user; avoid invoking git in stdlib-only context
    try:
        return getpass.getuser()
    except Exception:
        return None


def _canonical_agent(agent: str, registry: dict | None = None) -> str:
    a, tag = _split_agent_and_tag(agent.strip())
    canon = (a.lower() if a else "").strip()
    mapping = (registry or {}).get("aliases", {}) if registry else {}
    canon = mapping.get(canon, canon)
    return f"{canon}#{tag}" if tag else canon


def _counterpart_of(agent: str, registry: dict | None = None) -> str:
    mapping = (registry or {}).get("counterparts", {}) if registry else {"codex": "claude", "claude": "codex"}
    base, tag = _split_agent_and_tag(_canonical_agent(agent, registry))
    other = mapping.get(base, base)
    return f"{other}#{tag}" if tag else other


def _default_agent_and_role(registry: dict | None = None) -> tuple[str, str]:
    user = _get_git_user() or "user"
    default = (registry or {}).get("default", "codex") if registry else "codex"
    return default, user
