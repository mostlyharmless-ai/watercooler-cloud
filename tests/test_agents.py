from __future__ import annotations

from watercooler.agents import (
    _canonical_agent,
    _counterpart_of,
    _split_agent_and_tag,
    _default_agent_and_role,
)


def test_split_and_canonical():
    reg = {"aliases": {"gpt": "codex"}}
    a, tag = _split_agent_and_tag("gpt#dev")
    assert a == "gpt" and tag == "dev"
    assert _canonical_agent("gpt#dev", reg) == "codex#dev"


def test_counterpart_and_default():
    reg = {"counterparts": {"codex": "claude", "claude": "codex"}, "default": "codex"}
    assert _counterpart_of("codex", reg) == "claude"
    agent, role = _default_agent_and_role(reg)
    assert agent == "codex" and isinstance(role, str) and role

