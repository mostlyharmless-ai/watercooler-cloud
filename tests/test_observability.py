import json
import logging
import importlib.util
from pathlib import Path

# Import module directly from file to avoid importing package __init__ (which pulls fastmcp)
_OBS_PATH = Path("src/watercooler_mcp/observability.py").resolve()
spec = importlib.util.spec_from_file_location("watercooler_mcp_observability", _OBS_PATH)
obs = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(obs)  # type: ignore[attr-defined]

log_action = obs.log_action
timeit = obs.timeit
LOGGER_NAME = obs.LOGGER_NAME


def test_log_action_emits_json(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    log_action("git.pull", outcome="ok", duration_ms=123, topic="t1", agent="Codex")
    assert caplog.records
    msg = caplog.records[-1].message
    data = json.loads(msg)
    assert data["action"] == "git.pull"
    assert data["outcome"] == "ok"
    assert data["duration_ms"] == 123
    assert data["topic"] == "t1"
    assert data["agent"] == "Codex"


def test_timeit_success_logs(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    with timeit("test.block", topic="t2"):
        pass
    msg = caplog.records[-1].message
    data = json.loads(msg)
    assert data["action"] == "test.block"
    assert data["outcome"] == "ok"
    assert data["topic"] == "t2"
    assert isinstance(data["duration_ms"], (int, float))


def test_timeit_error_logs(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    try:
        with timeit("test.err", topic="t3"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    msg = caplog.records[-1].message
    data = json.loads(msg)
    assert data["action"] == "test.err"
    assert data["outcome"] == "error"
    assert data["topic"] == "t3"
