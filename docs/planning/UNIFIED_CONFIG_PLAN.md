# Unified Configuration System for Watercooler-Cloud

**Date:** 2024-12-24
**Status:** Planned
**Priority:** P1 (Moderate Issues - per ARCHITECTURAL_REVIEW.md)

---

## Goal

Consolidate the fragmented configuration system (currently 6 modules) into a unified facade that makes config easy to use while maintaining backward compatibility.

---

## Current Problems

1. **Duplication**: Path resolution logic duplicated between `watercooler/config.py` and `watercooler_mcp/config.py`
2. **No single entry point**: Mix of `resolve_X()`, `get_X()`, dataclass access, and direct `os.getenv()` calls
3. **Scattered env vars**: Direct `os.getenv()` in 10+ files
4. **Credentials overlap**: `credentials.py` duplicates TOML loading from `config_loader.py`
5. **Hard to test**: Requires mocking multiple functions + env vars

---

## Current State Analysis

### Configuration Modules (6 Total)

1. **`watercooler/config.py`** - Stdlib-only path resolution
   - Thread directory discovery (git-aware)
   - Template directory resolution
   - Direct subprocess git calls

2. **`watercooler/config_loader.py`** - TOML loading & merging
   - Discovers and merges: defaults → user → project → env
   - Thread-safe caching via `get_config()`
   - Pydantic validation

3. **`watercooler/config_schema.py`** - Pydantic models
   - WatercoolerConfig root with nested sections
   - CommonConfig, McpConfig, GitConfig, SyncConfig, LoggingConfig, etc.

4. **`watercooler/credentials.py`** - Credential management
   - Loads ~/.watercooler/credentials.toml (with JSON migration)
   - **DUPLICATION**: Also loads config.toml for memory_graph section
   - Getters: `get_github_token()`, `get_ssh_key_path()`, `get_deepseek_api_key()`

5. **`watercooler_mcp/config.py`** - MCP runtime context
   - `resolve_thread_context()` - Returns ThreadContext dataclass
   - GitPython-based git discovery (to avoid Windows subprocess hangs)
   - **DUPLICATION**: Path resolution logic similar to watercooler/config.py
   - Config system integration via lazy import

6. **`watercooler_memory/pipeline/config.py`** - Pipeline config
   - Loads .env.pipeline file
   - Uses credentials module for API keys

### Identified Overlap

- **Path resolution**: Both `watercooler/config.py` (subprocess) and `watercooler_mcp/config.py` (GitPython) implement similar git discovery
- **TOML loading**: `credentials.py` duplicates TOML loading from `config_loader.py`
- **Environment variables**: Scattered `os.getenv()` calls across 10+ files with duplicated parsing logic

---

## Solution Overview

Create a **unified facade** (`config_facade.py`) as single entry point while consolidating duplicated path resolution into `path_resolver.py`.

### New API (After Phase 1)

```python
from watercooler.config_facade import config

# Simple path access (lightweight)
threads_dir = config.paths.threads_dir
templates_dir = config.paths.templates_dir

# Full config access (lazy-loaded TOML + Pydantic)
cfg = config.full()
log_level = cfg.mcp.logging.level

# Runtime context (MCP)
ctx = config.context(code_root="/path/to/repo")

# Environment variables (centralized with type helpers)
agent = config.env.get("WATERCOOLER_AGENT", "Agent")
auto = config.env.get_bool("WATERCOOLER_AUTO_PROVISION", True)
port = config.env.get_int("WATERCOOLER_PORT", 8080)

# Credentials
token = config.get_github_token()
```

---

## Implementation Plan

### Phase 1: Foundation (Comprehensive - No Breaking Changes)

**Goal**: Create facade + path resolver in one go, fully backward compatible

#### 1.1 Create `src/watercooler/path_resolver.py` (NEW)

Consolidate git-aware path discovery from both `config.py` and `watercooler_mcp/config.py`:

```python
"""Unified path resolution for threads and templates.

Consolidates git-aware path discovery logic used by both
the core library and MCP server.
"""

from pathlib import Path
from typing import Optional, Tuple
import os
import subprocess


class GitInfo:
    """Git repository information from subprocess git calls."""

    def __init__(self, root: Optional[Path], branch: Optional[str],
                 commit: Optional[str], remote: Optional[str]):
        self.root = root
        self.branch = branch
        self.commit = commit
        self.remote = remote


def discover_git_info(code_root: Optional[Path]) -> GitInfo:
    """Discover git repository info using subprocess.

    Consolidates logic from watercooler/config.py and watercooler_mcp/config.py.
    Uses subprocess git calls (no GitPython dependency).
    """
    # Unified implementation using subprocess
    # Replaces duplicated logic in both config.py files


def resolve_threads_dir(
    cli_value: Optional[str] = None,
    code_root: Optional[Path] = None
) -> Path:
    """Resolve threads directory with precedence: CLI > env > git-aware default.

    Consolidates logic from both watercooler/config.py and watercooler_mcp/config.py.
    """
    # Consolidates logic from both modules


def resolve_templates_dir(cli_value: Optional[str] = None) -> Path:
    """Resolve templates directory with fallback chain.

    Precedence:
    1. CLI argument
    2. WATERCOOLER_TEMPLATES env var
    3. Project-local .watercooler/templates/
    4. Package bundled templates
    """
    # From watercooler/config.py
```

**Key changes**:
- Unifies `_run_git()` and `_discover_git()` from both modules
- Uses subprocess uniformly (no GitPython requirement)
- Single source of truth for path resolution
- ~200 lines

#### 1.2 Create `src/watercooler/config_facade.py` (NEW)

Unified facade providing single entry point:

```python
"""Unified configuration facade for watercooler-cloud.

Single entry point for all configuration access:
- Path resolution (threads_dir, templates_dir)
- TOML config loading (user + project)
- Credential management
- Environment variable access
- Runtime context (for MCP)
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
import os


@dataclass(frozen=True)
class PathConfig:
    """Resolved filesystem paths."""
    threads_dir: Path
    templates_dir: Path
    code_root: Optional[Path] = None


class Config:
    """Unified configuration facade.

    Usage:
        from watercooler.config_facade import config

        # Simple paths (lightweight, stdlib-only)
        threads_dir = config.paths.threads_dir

        # Full config (lazy-loads TOML + Pydantic)
        cfg = config.full()

        # Runtime context (MCP)
        ctx = config.context(code_root)

        # Environment access (centralized with type helpers)
        level = config.env.get("WATERCOOLER_LOG_LEVEL", "INFO")
        enabled = config.env.get_bool("WATERCOOLER_FEATURE", True)
    """

    def __init__(self):
        self._full_config = None
        self._credentials = None
        self._paths = None

    @property
    def paths(self) -> PathConfig:
        """Get resolved paths (lightweight, stdlib-only)."""
        if self._paths is None:
            from .path_resolver import resolve_threads_dir, resolve_templates_dir
            self._paths = PathConfig(
                threads_dir=resolve_threads_dir(),
                templates_dir=resolve_templates_dir()
            )
        return self._paths

    def full(self, project_path: Optional[Path] = None, force_reload: bool = False):
        """Get full configuration (lazy-loads TOML + Pydantic)."""
        if force_reload or self._full_config is None:
            from .config_loader import get_config
            self._full_config = get_config(project_path, force_reload)
        return self._full_config

    @property
    def credentials(self):
        """Get credentials (lazy-loads ~/.watercooler/credentials.toml)."""
        if self._credentials is None:
            from .credentials import load_credentials
            self._credentials = load_credentials()
        return self._credentials

    def context(self, code_root: Optional[Path] = None):
        """Resolve runtime thread context (MCP)."""
        from watercooler_mcp.config import resolve_thread_context
        return resolve_thread_context(code_root)

    # Centralized environment variable access
    class EnvVars:
        """Environment variable helpers with type coercion."""

        @staticmethod
        def get(key: str, default: Any = None) -> Any:
            """Get environment variable."""
            return os.getenv(key, default)

        @staticmethod
        def get_bool(key: str, default: bool = False) -> bool:
            """Get boolean environment variable.

            Treats "1", "true", "yes", "on" as True (case-insensitive).
            """
            val = os.getenv(key, "").lower()
            if not val:
                return default
            return val in ("1", "true", "yes", "on")

        @staticmethod
        def get_int(key: str, default: int = 0) -> int:
            """Get integer environment variable."""
            val = os.getenv(key)
            if val:
                try:
                    return int(val)
                except ValueError:
                    pass
            return default

        @staticmethod
        def get_path(key: str, default: Optional[Path] = None) -> Optional[Path]:
            """Get path environment variable with expansion."""
            val = os.getenv(key)
            if val:
                return Path(os.path.expanduser(os.path.expandvars(val)))
            return default

    env = EnvVars()

    # Helper methods
    def get_threads_dir(self, cli_value: Optional[str] = None,
                       code_root: Optional[Path] = None) -> Path:
        """Resolve threads directory with precedence: CLI > env > git-aware default."""
        from .path_resolver import resolve_threads_dir
        return resolve_threads_dir(cli_value, code_root)

    def get_github_token(self) -> Optional[str]:
        """Get GitHub token from env or credentials file.

        Precedence: GITHUB_TOKEN env > GH_TOKEN env > credentials.toml
        """
        token = self.env.get("GITHUB_TOKEN") or self.env.get("GH_TOKEN")
        if token:
            return token
        return self.credentials.github.token or None

    def reset(self) -> None:
        """Reset cached state (for testing)."""
        self._full_config = None
        self._credentials = None
        self._paths = None


# Global singleton
config = Config()
```

**Key features**:
- Lazy loading (paths, full config, credentials)
- Centralized env var access with type helpers
- Thread-safe through existing locks in underlying modules
- Clean namespace (`config.paths`, `config.env`, `config.full()`)
- ~250 lines

#### 1.3 Create `src/watercooler/testing.py` (NEW)

Testing utilities with context managers AND pytest fixtures:

```python
"""Testing utilities for configuration.

Provides clean interfaces for injecting test configuration
without environment variable pollution.
"""

from contextlib import contextmanager
from typing import Dict, Any, Optional
from pathlib import Path
import pytest
import os


@contextmanager
def temp_config(
    threads_dir: Optional[Path] = None,
    env_overrides: Optional[Dict[str, str]] = None,
    config_dict: Optional[Dict[str, Any]] = None
):
    """Temporarily override configuration for testing.

    Example:
        with temp_config(
            threads_dir="/tmp/test-threads",
            env_overrides={"WATERCOOLER_LOG_LEVEL": "DEBUG"}
        ):
            # Test code here
            assert config.paths.threads_dir == Path("/tmp/test-threads")
    """
    from .config_facade import config

    # Save state
    old_paths = config._paths
    old_full = config._full_config
    old_creds = config._credentials
    old_env = {}

    try:
        # Apply overrides
        if env_overrides:
            for key, value in env_overrides.items():
                old_env[key] = os.environ.get(key)
                os.environ[key] = value

        if threads_dir:
            from .config_facade import PathConfig
            config._paths = PathConfig(
                threads_dir=threads_dir,
                templates_dir=config.paths.templates_dir
            )

        if config_dict:
            from .config_schema import WatercoolerConfig
            config._full_config = WatercoolerConfig.model_validate(config_dict)

        yield config

    finally:
        # Restore state
        config._paths = old_paths
        config._full_config = old_full
        config._credentials = old_creds

        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextmanager
def mock_env_vars(**env_vars):
    """Temporarily set environment variables for testing.

    Example:
        with mock_env_vars(WATERCOOLER_LOG_LEVEL="DEBUG"):
            assert os.getenv("WATERCOOLER_LOG_LEVEL") == "DEBUG"
    """
    old_env = {}

    try:
        for key, value in env_vars.items():
            old_env[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)

        yield

    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


# Pytest fixtures
@pytest.fixture
def clean_config():
    """Reset config to clean state.

    Usage:
        def test_something(clean_config):
            assert clean_config.paths.threads_dir is not None
    """
    from .config_facade import config
    config.reset()
    yield config
    config.reset()


@pytest.fixture
def temp_threads_dir(tmp_path):
    """Provide temporary threads directory.

    Usage:
        def test_something(temp_threads_dir):
            # temp_threads_dir is Path to tmp/threads
            assert temp_threads_dir.exists()
    """
    threads = tmp_path / "threads"
    threads.mkdir()
    with temp_config(threads_dir=threads):
        yield threads


@pytest.fixture
def mock_watercooler_env():
    """Context manager for mocking WATERCOOLER_* env vars.

    Usage:
        def test_something(mock_watercooler_env):
            with mock_watercooler_env(WATERCOOLER_LOG_LEVEL="DEBUG"):
                assert config.env.get("WATERCOOLER_LOG_LEVEL") == "DEBUG"
    """
    return mock_env_vars
```

**Key features**:
- Context managers for flexible use
- Pytest fixtures for common scenarios
- Automatic cleanup
- ~150 lines

#### 1.4 Update `src/watercooler/credentials.py` (MODIFY)

Remove TOML loading duplication:

```python
def get_memory_graph_config() -> Dict[str, Any]:
    """Get memory_graph section from config.toml."""
    # OLD: Duplicate TOML loading
    # config = _load_config()
    # return config.get("memory_graph", {})

    # NEW: Delegate to config system
    try:
        from .config_facade import config
        full_config = config.full()
        return getattr(full_config, "memory_graph", {})
    except Exception:
        return {}
```

**Change**: Eliminates duplicate TOML loading by delegating to config_loader.

#### 1.5 Update `src/watercooler/config.py` (MODIFY)

Make it delegate to path_resolver:

```python
"""Legacy path resolution (backward compatibility).

DEPRECATED: Use config_facade instead.

This module is maintained for backward compatibility only.
New code should use:
    from watercooler.config_facade import config
    threads_dir = config.paths.threads_dir
"""

def resolve_threads_dir(cli_value: Optional[str] = None) -> Path:
    """Resolve threads directory.

    DEPRECATED: Use config.get_threads_dir() instead.
    """
    from .path_resolver import resolve_threads_dir as _resolve
    return _resolve(cli_value)


def resolve_templates_dir(cli_value: Optional[str] = None) -> Path:
    """Resolve templates directory.

    DEPRECATED: Use config.paths.templates_dir instead.
    """
    from .path_resolver import resolve_templates_dir as _resolve
    return _resolve(cli_value)


def load_template(name: str, templates_dir: Optional[Path] = None) -> str:
    """Load template file (no change - still actively used)."""
    # Keep existing implementation
```

**Change**: Becomes thin wrapper around path_resolver for backward compatibility.

#### 1.6 Update `src/watercooler_mcp/config.py` (MODIFY)

Use shared path_resolver for git discovery:

```python
from watercooler.path_resolver import discover_git_info

def _discover_git(code_root: Optional[Path]) -> _GitDetails:
    """Discover git repository info using shared path_resolver."""
    # OLD: Local implementation with GitPython
    # NEW: Delegate to shared path_resolver (subprocess-based)
    git_info = discover_git_info(code_root)
    return _GitDetails(
        root=git_info.root,
        branch=git_info.branch,
        commit=git_info.commit,
        remote=git_info.remote
    )
```

**Change**: Removes duplicated git discovery logic. Note: This removes the GitPython dependency from this module, switching to subprocess uniformly.

#### 1.7 Add Tests (NEW)

Create comprehensive test coverage:

- `tests/test_config_facade.py` - Facade integration tests
- `tests/test_path_resolver.py` - Path resolution unit tests
- `tests/test_config_testing_utils.py` - Testing utilities tests

**Files Modified in Phase 1**:
- ✨ NEW: `src/watercooler/path_resolver.py` (~200 lines)
- ✨ NEW: `src/watercooler/config_facade.py` (~250 lines)
- ✨ NEW: `src/watercooler/testing.py` (~150 lines)
- 📝 MODIFY: `src/watercooler/credentials.py` (1 function change)
- 📝 MODIFY: `src/watercooler/config.py` (become thin wrappers)
- 📝 MODIFY: `src/watercooler_mcp/config.py` (use path_resolver)
- ✨ NEW: `tests/test_config_facade.py`
- ✨ NEW: `tests/test_path_resolver.py`
- ✨ NEW: `tests/test_config_testing_utils.py`

**Backward Compatibility**: 100% - All existing imports continue working

---

### Phase 2: Migration (Deprecation Warnings)

**Goal**: Migrate internal code to use facade, add deprecation warnings

#### 2.1 Migrate Internal Code

Update files with scattered `os.getenv()` calls:

- `src/watercooler_mcp/observability.py` - Use `config.env.get()` for log settings
- `src/watercooler_mcp/provisioning.py` - Use `config.env.get_bool()` for flags
- `src/watercooler_mcp/git_sync.py` - Use `config.env` for sync settings
- `src/watercooler_mcp/server.py` - Use facade for config access

**Pattern**:
```python
# Before
level = os.getenv("WATERCOOLER_LOG_LEVEL", "INFO")
auto = os.getenv("WATERCOOLER_AUTO_PROVISION", "1").lower() in TRUE_VALUES

# After
from watercooler.config_facade import config
level = config.env.get("WATERCOOLER_LOG_LEVEL", "INFO")
auto = config.env.get_bool("WATERCOOLER_AUTO_PROVISION", True)
```

#### 2.2 Add Deprecation Warnings

Update legacy entry points:

```python
# src/watercooler/config.py
import warnings

def resolve_threads_dir(cli_value: Optional[str] = None) -> Path:
    warnings.warn(
        "resolve_threads_dir is deprecated, use config.get_threads_dir() instead",
        DeprecationWarning,
        stacklevel=2
    )
    from .config_facade import config
    return config.get_threads_dir(cli_value)
```

#### 2.3 Update Documentation

- Create `docs/configuration.md` - User guide for unified config system
- Update `README.md` - Show new facade API
- Update `CLAUDE.md` - Reflect new config patterns

**Files Modified in Phase 2**:
- 📝 MODIFY: `src/watercooler_mcp/observability.py`
- 📝 MODIFY: `src/watercooler_mcp/provisioning.py`
- 📝 MODIFY: `src/watercooler_mcp/git_sync.py`
- 📝 MODIFY: `src/watercooler_mcp/server.py`
- 📝 MODIFY: `src/watercooler/config.py` (add warnings)
- 📝 MODIFY: `src/watercooler/config_loader.py` (add warnings)
- ✨ NEW: `docs/configuration.md`
- 📝 UPDATE: `README.md`, `CLAUDE.md`

**Backward Compatibility**: 100% - Old imports work with deprecation warnings

---

### Phase 3: Cleanup & Documentation

**Goal**: Polish, document, and optimize

#### 3.1 Code Cleanup

- Remove unused imports from refactored modules
- Simplify `watercooler/config.py` to bare minimum shims
- Optimize lazy loading performance

#### 3.2 Complete Documentation

- Add docstring examples to all facade methods
- Create migration guide for external users
- Add configuration guide to main docs

#### 3.3 Performance Validation

- Benchmark config access patterns
- Ensure lazy loading doesn't add overhead
- Validate caching works correctly

**Files Modified in Phase 3**:
- 📝 REFACTOR: `src/watercooler/config.py`
- ✨ NEW: `docs/migration/unified-config.md`
- 📝 UPDATE: All docstrings in facade modules

**Backward Compatibility**: 95% - Old imports work but emit warnings

---

### Phase 4: Future (Optional - Next Major Version)

**Goal**: Remove deprecated APIs (with proper deprecation cycle)

- Remove old entry points (after 6+ month deprecation)
- Simplify module structure
- Performance optimizations

---

## Success Criteria

### Phase 1 Complete When:
- ✅ `config.paths.threads_dir` works
- ✅ `config.full()` loads TOML correctly
- ✅ `config.env.get_bool()` parses env vars
- ✅ All existing imports still work (no breakage)
- ✅ Tests pass (new + existing)
- ✅ No duplication between config.py and watercooler_mcp/config.py

### Phase 2 Complete When:
- ✅ Internal code uses facade
- ✅ Deprecation warnings in place
- ✅ Documentation updated
- ✅ Tests still pass

### User Benefits:
1. **Single entry point**: `from watercooler.config_facade import config`
2. **Type-safe env access**: `config.env.get_bool()` instead of manual parsing
3. **Easy testing**: `with temp_config(threads_dir=...)` + pytest fixtures
4. **Clear precedence**: CLI > Env > Project TOML > User TOML > Defaults
5. **No duplication**: Single git discovery implementation

---

## Critical Files

### Phase 1 (Foundation):
- `src/watercooler/path_resolver.py` - NEW (unified git discovery)
- `src/watercooler/config_facade.py` - NEW (unified facade)
- `src/watercooler/testing.py` - NEW (test utilities + fixtures)
- `src/watercooler/credentials.py` - MODIFY (remove TOML duplication)
- `src/watercooler/config.py` - MODIFY (delegate to path_resolver)
- `src/watercooler_mcp/config.py` - MODIFY (use path_resolver)
- `tests/test_config_facade.py` - NEW
- `tests/test_path_resolver.py` - NEW
- `tests/test_config_testing_utils.py` - NEW

### Phase 2 (Migration):
- `src/watercooler_mcp/observability.py`
- `src/watercooler_mcp/provisioning.py`
- `src/watercooler_mcp/git_sync.py`
- `src/watercooler_mcp/server.py`
- `docs/configuration.md` - NEW

---

## Notes

- **No new dependencies**: Uses subprocess uniformly (no GitPython requirement)
- **Backward compatible**: All existing code keeps working through Phase 3
- **Incremental**: Can ship Phase 1 independently, then migrate at own pace
- **Testable**: Clean injection via context managers and pytest fixtures
- **Performance**: Lazy loading ensures no overhead for simple use cases
- **Addresses ARCHITECTURAL_REVIEW.md Section 2.2.3**: Consolidates configuration system fragmentation

---

## References

- **Architectural Review**: docs/planning/ARCHITECTURAL_REVIEW.md (Section 2.2.3)
- **Related Work**: Memory Backend Integration Plan (docs/planning/MEMORY_BACKEND_INTEGRATION_PLAN.md)
