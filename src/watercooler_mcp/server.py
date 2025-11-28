"""Watercooler MCP Server - Phase 1A MVP

FastMCP server exposing watercooler-cloud tools to AI agents.
All tools are namespaced as watercooler_v1_* for provider compatibility.

Phase 1A features:
- 7 core tools + 2 diagnostic tools
- Markdown-only output (format param accepted but unused)
- Simple env-based config (WATERCOOLER_AGENT, WATERCOOLER_DIR)
- Basic error handling with helpful messages
"""

import sys
if sys.version_info < (3, 10):
    raise RuntimeError(
        f"Watercooler MCP requires Python 3.10+; found {sys.version.split()[0]}"
    )

# Standard library imports
import json
import os
import re
import time
from pathlib import Path
from typing import Callable, TypeVar, Optional, Dict, List

# Third-party imports
from fastmcp import FastMCP, Context
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
from ulid import ULID
from git import Repo, InvalidGitRepositoryError, GitCommandError

# Local application imports
from watercooler import commands, fs
from watercooler.metadata import thread_meta
from watercooler.thread_entries import ThreadEntry, parse_thread_entries
from .config import (
    ThreadContext,
    get_agent_name,
    get_threads_dir,
    get_version,
    get_git_sync_manager_from_context,
    resolve_thread_context,
)
from .git_sync import (
    GitPushError,
    BranchPairingError,
    BranchMismatch,
    BranchPairingResult,
    validate_branch_pairing,
    GitSyncManager,
    sync_branch_history,
    BranchSyncResult,
    BranchDivergenceInfo,
    _find_main_branch,
)
from .observability import log_debug, log_action, log_warning, log_error, timeit

# Workaround for Windows stdio hang: Force auto-flush on every stdout write
# On Windows, FastMCP's stdio transport gets stuck after subprocess operations
# Auto-flushing after every write prevents response from getting stuck in buffer
if sys.platform == "win32":
    import io

    class AutoFlushWrapper(io.TextIOWrapper):
        def write(self, s):
            result = super().write(s)
            self.flush()
            return result

    # Wrap stdout with auto-flush
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = AutoFlushWrapper(
            sys.stdout.buffer,
            encoding=sys.stdout.encoding,
            errors=sys.stdout.errors,
            newline=None,
            line_buffering=False,
            write_through=True
        )

# Initialize FastMCP server with configurable transport
# WATERCOOLER_MCP_TRANSPORT: "http" or "stdio" (default: "stdio" for backward compatibility)
_TRANSPORT = os.getenv("WATERCOOLER_MCP_TRANSPORT", "stdio").lower()
mcp = FastMCP(name="Watercooler Cloud")


# Instrument FastMCP tool execution for observability
try:
    from fastmcp.tools.tool import FunctionTool  # type: ignore

    _orig_run = FunctionTool.run

    async def _instrumented_run(self, arguments):  # type: ignore
        tool_name = getattr(self, 'name', '<unknown>')
        input_chars = len(json.dumps(arguments)) if arguments else 0
        start_time = time.perf_counter()
        outcome = "ok"
        try:
            result = await _orig_run(self, arguments)
            return result
        except Exception:
            outcome = "error"
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            try:
                log_action(
                    "mcp.tool",
                    tool_name=tool_name,
                    input_chars=input_chars,
                    duration_ms=duration_ms,
                    outcome=outcome,
                )
                # Workaround: Force stdout flush on Windows after tool execution
                if sys.platform == "win32":
                    sys.stdout.flush()
                    sys.stderr.flush()
            except Exception:
                pass

    FunctionTool.run = _instrumented_run  # type: ignore
except Exception:
    pass


T = TypeVar("T")


def _should_auto_branch() -> bool:
    return os.getenv("WATERCOOLER_AUTO_BRANCH", "1") != "0"


def _require_context(code_path: str) -> tuple[str | None, ThreadContext | None]:
    log_debug(f"_require_context: entry with code_path={code_path!r}")
    if not code_path:
        return (
            "code_path required: pass the code repository root (e.g., '.') so the server can resolve the correct threads repo/branch.",
            None,
        )

    # Handle WSL-style absolute paths on Windows (e.g., /C/Users/...)
    if os.name == "nt" and code_path.startswith("/") and len(code_path) > 2:
        drive = code_path[1]
        if drive.isalpha() and code_path[2] == "/":
            code_path = f"{drive}:{code_path[2:].replace('/', os.sep)}"
    if os.getenv("WATERCOOLER_DEBUG_CODE_PATH", "0") not in {"0", "false", "off"}:
        log_dir = os.getenv("WATERCOOLER_DEBUG_LOG_DIR")
        log_path = Path(log_dir).resolve() if log_dir else Path.home() / ".watercooler-codepath-debug.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"cwd={Path.cwd()} input={code_path!r}\n")
        except Exception:
            pass
    try:
        log_debug(f"_require_context: calling resolve_thread_context({code_path!r})")
        context = resolve_thread_context(Path(code_path))
        log_debug(f"_require_context: resolve_thread_context returned")
    except Exception as exc:
        log_debug(f"_require_context: exception from resolve_thread_context: {exc}")
        return (f"Error resolving code context: {exc}", None)
    log_debug(f"_require_context: exit, returning context")
    return (None, context)


def _dynamic_context_missing(context: ThreadContext) -> bool:
    dynamic_env = any(
        os.getenv(key)
        for key in (
            "WATERCOOLER_THREADS_BASE",
            "WATERCOOLER_THREADS_PATTERN",
            "WATERCOOLER_GIT_REPO",
            "WATERCOOLER_CODE_REPO",
        )
    )
    return dynamic_env and not context.explicit_dir and context.threads_slug is None


def _attempt_auto_fix_divergence(
    context: ThreadContext,
    validation_result: BranchPairingResult,
) -> Optional[BranchPairingResult]:
    """Attempt to auto-fix branch history divergence via rebase.

    Args:
        context: Thread context with code and threads repo info
        validation_result: The failed validation result containing divergence info

    Returns:
        New BranchPairingResult on successful fix, None on failure.
        On failure, raises BranchPairingError with details.

    Raises:
        BranchPairingError: If auto-fix fails and requires manual intervention
    """
    log_debug("Detected branch history divergence, attempting auto-fix via rebase")

    # Check if this is a "behind-main" divergence (threads behind main but code not)
    # vs a local-vs-origin divergence. They require different fix strategies.
    behind_main_mismatch = None
    for mismatch in validation_result.mismatches:
        if (mismatch.type == "branch_history_diverged" and
                "behind main" in mismatch.recovery.lower()):
            behind_main_mismatch = mismatch
            break

    # Determine the target for rebase
    onto_branch: Optional[str] = None
    if behind_main_mismatch:
        # Need to rebase onto main, not origin/branch
        try:
            threads_repo = Repo(context.threads_dir, search_parent_directories=True)
            onto_branch = _find_main_branch(threads_repo)
            if onto_branch:
                log_debug(f"Behind-main divergence detected, will rebase onto {onto_branch}")
            else:
                log_debug("Behind-main divergence detected but couldn't find main branch")
        except Exception as e:
            log_debug(f"Error finding main branch: {e}")

    try:
        sync_result = sync_branch_history(
            threads_repo_path=context.threads_dir,
            branch=validation_result.threads_branch or context.code_branch,
            strategy="rebase",
            force=True,  # Uses --force-with-lease for safety
            onto=onto_branch,  # None for origin/branch, "main" for behind-main fix
        )

        if not sync_result.success:
            log_debug(f"Auto-fix failed: {sync_result.details}")
            error_parts = [
                "Branch history divergence detected and auto-fix failed:",
                f"  Code branch: {validation_result.code_branch or '(detached/unknown)'}",
                f"  Threads branch: {validation_result.threads_branch or '(detached/unknown)'}",
                f"  Fix attempt: {sync_result.details}",
            ]
            if sync_result.needs_manual_resolution:
                error_parts.append("  Manual resolution required.")
            error_parts.append(
                "\nManual recovery: watercooler_v1_sync_branch_state with operation='recover'"
            )
            raise BranchPairingError("\n".join(error_parts))

        log_debug(f"Auto-fixed branch divergence: {sync_result.details}")

        # Re-validate to confirm fix worked
        revalidation = validate_branch_pairing(
            code_repo=context.code_root,
            threads_repo=context.threads_dir,
            strict=True,
            check_history=True,
        )

        if revalidation.valid:
            log_debug("Branch pairing now valid after auto-fix")
            return revalidation
        else:
            log_debug(f"Auto-fix completed but validation still failing: {revalidation.warnings}")
            # Return the updated result so caller can report remaining issues
            return revalidation

    except BranchPairingError:
        raise
    except Exception as fix_error:
        log_debug(f"Auto-fix exception: {fix_error}")
        error_parts = [
            "Branch history divergence detected, auto-fix failed:",
            f"  Code branch: {validation_result.code_branch or '(detached/unknown)'}",
            f"  Threads branch: {validation_result.threads_branch or '(detached/unknown)'}",
            f"  Error: {fix_error}",
            "\nManual recovery: watercooler_v1_sync_branch_state with operation='recover'"
        ]
        raise BranchPairingError("\n".join(error_parts))


def _validate_and_sync_branches(
    context: ThreadContext,
    skip_validation: bool = False,
) -> None:
    """Validate branch pairing and sync branches if needed.

    This helper is used by both read and write operations to ensure
    the threads repo is on the correct branch before any operation.

    Includes automatic detection and repair of:
    1. Branch name mismatch: Checks out threads repo to match code repo branch
    2. Branch history divergence: Rebases threads branch after code repo rebase/force-push

    When auto-fix is enabled (WATERCOOLER_AUTO_BRANCH=1, default), these issues
    are resolved automatically. If auto-fix fails, raises BranchPairingError.

    Side effects:
        - May checkout threads repo to different branch
        - May rebase threads branch to match code branch history
        - May push to remote with --force-with-lease if divergence detected
        - Blocks operation if conflicts occur during auto-fix

    Args:
        context: Thread context with code and threads repo info
        skip_validation: If True, skip strict validation (used for recovery operations)

    Raises:
        BranchPairingError: If branch validation fails and auto-fix is not possible,
                           or if auto-fix encounters conflicts requiring manual resolution
    """
    sync = get_git_sync_manager_from_context(context)
    if not sync:
        return

    # Validate branch pairing before any operation
    if not skip_validation and context.code_root and context.threads_dir:
        try:
            validation_result = validate_branch_pairing(
                code_repo=context.code_root,
                threads_repo=context.threads_dir,
                strict=True,
                check_history=True,  # Enable divergence detection
            )
            if not validation_result.valid:
                # Check if this is a branch name mismatch we can auto-fix via checkout
                branch_mismatch: Optional[BranchMismatch] = next(
                    (m for m in validation_result.mismatches if m.type == "branch_name_mismatch"),
                    None
                )

                if branch_mismatch and context.code_branch and _should_auto_branch():
                    log_debug(f"Branch name mismatch detected, auto-fixing via checkout to {context.code_branch}")
                    try:
                        sync.ensure_branch(context.code_branch)
                        # Re-validate after branch checkout
                        validation_result = validate_branch_pairing(
                            code_repo=context.code_root,
                            threads_repo=context.threads_dir,
                            strict=True,
                            check_history=True,
                        )
                        if validation_result.valid:
                            log_debug(f"Branch name mismatch auto-fixed: checked out to {context.code_branch}")
                        else:
                            log_debug(f"Branch checkout completed but validation still failing: {validation_result.warnings}")
                    except Exception as e:
                        log_debug(f"Auto-fix branch checkout failed: {e}")

                # Check if this is a history divergence we can auto-fix
                history_mismatch: Optional[BranchMismatch] = next(
                    (m for m in validation_result.mismatches if m.type == "branch_history_diverged"),
                    None
                )

                if history_mismatch:
                    # Attempt auto-fix - may raise BranchPairingError on failure
                    validation_result = _attempt_auto_fix_divergence(context, validation_result)

                # Unified error reporting for any remaining validation failures
                # (non-history issues, or edge case where auto-fix succeeded but other mismatches remain)
                if not validation_result.valid:
                    error_parts = [
                        "Branch pairing validation failed:",
                        f"  Code branch: {validation_result.code_branch or '(detached/unknown)'}",
                        f"  Threads branch: {validation_result.threads_branch or '(detached/unknown)'}",
                    ]
                    if validation_result.mismatches:
                        error_parts.append("\nMismatches:")
                        for mismatch in validation_result.mismatches:
                            error_parts.append(f"  - {mismatch.type}: {mismatch.recovery}")
                    if validation_result.warnings:
                        error_parts.append("\nWarnings:")
                        for warning in validation_result.warnings:
                            error_parts.append(f"  - {warning}")
                    error_parts.append(
                        "\nRun: watercooler_v1_sync_branch_state with operation='checkout' to sync branches"
                    )
                    raise BranchPairingError("\n".join(error_parts))
        except BranchPairingError:
            raise
        except Exception as e:
            # Log but don't block on validation errors (e.g., repo not initialized)
            log_debug(f"Branch validation warning: {e}")

    # Attempt to sync branches (catch exceptions to avoid blocking legitimate operations)
    branch = context.code_branch
    if branch and _should_auto_branch():
        try:
            sync.ensure_branch(branch)
        except Exception:
            pass


def _refresh_threads(context: ThreadContext, skip_validation: bool = False) -> None:
    """Refresh threads repo by validating branch pairing and pulling latest changes.
    
    Args:
        context: Thread context with repo information
        skip_validation: If True, skip branch validation (used for recovery operations)
        
    Raises:
        BranchPairingError: If branch validation fails and skip_validation=False
    """
    # Validate and sync branches (will raise if validation fails)
    _validate_and_sync_branches(context, skip_validation=skip_validation)
    
    sync = get_git_sync_manager_from_context(context)
    if not sync:
        return
        
    status = sync.get_async_status()
    if status.get("mode") == "async":
        # Async mode relies on background pulls; avoid blocking operations.
        return
    sync.pull()


_ALLOWED_FORMATS = {"markdown", "json"}

# Resource limits to prevent exhaustion
_MAX_LIMIT = 1000  # Maximum entries that can be requested in a single call
_MAX_OFFSET = 100000  # Maximum offset to prevent excessive memory usage

# Regex patterns for extracting thread metadata from content
_TITLE_RE = re.compile(r"^#\s*(?P<val>.+)$", re.MULTILINE)
_STAT_RE = re.compile(r"^Status:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
_BALL_RE = re.compile(r"^Ball:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
_ENTRY_RE = re.compile(r"^Entry:\s*(?P<who>.+?)\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s*$", re.MULTILINE)
_CLOSED_STATES = {"done", "closed", "merged", "resolved", "abandoned", "obsolete"}


def _normalize_status(s: str) -> str:
    """Normalize status string to lowercase."""
    return s.strip().lower()


def _extract_thread_metadata(content: str, topic: str) -> tuple[str, str, str, str]:
    """Extract thread metadata from content string without re-reading the file.

    Args:
        content: Full thread markdown content
        topic: Thread topic (used as fallback for title)

    Returns:
        Tuple of (title, status, ball, last_entry_timestamp)
    """
    title_match = _TITLE_RE.search(content)
    title = title_match.group("val").strip() if title_match else topic

    status_match = _STAT_RE.search(content)
    status = _normalize_status(status_match.group("val") if status_match else "open")

    ball_match = _BALL_RE.search(content)
    ball = ball_match.group("val").strip() if ball_match else "unknown"

    # Extract last entry timestamp
    hits = list(_ENTRY_RE.finditer(content))
    last = hits[-1].group("ts").strip() if hits else fs.utcnow_iso()

    return title, status, ball, last


def _resolve_format(value: str | None, *, default: str = "markdown") -> tuple[str | None, str]:
    fmt = (value or "").strip().lower()
    if not fmt:
        return (None, default)
    if fmt not in _ALLOWED_FORMATS:
        allowed = ", ".join(sorted(_ALLOWED_FORMATS))
        return (f"Error: unsupported format '{value}'. Allowed formats: {allowed}.", default)
    return (None, fmt)


def _load_thread_entries(topic: str, context: ThreadContext) -> tuple[str | None, list[ThreadEntry]]:
    """Load and parse thread entries from disk.

    Thread Safety Note:
        This function performs unlocked reads. This is safe because:
        - Write operations (say, ack, handoff) use AdvisoryLock for serialization
        - Reads may see partially written entries, but won't corrupt existing ones
        - Thread entry boundaries (---) ensure partial writes don't break parsing
        - File system guarantees atomic writes at the block level
        - MCP tool calls are typically infrequent enough that read/write races are rare

    For high-concurrency scenarios, consider adding shared/exclusive locking
    or caching with mtime-based invalidation.
    """
    threads_dir = context.threads_dir
    thread_path = fs.thread_path(topic, threads_dir)

    if not thread_path.exists():
        if threads_dir.exists():
            available_list = sorted(p.stem for p in threads_dir.glob("*.md"))
            if len(available_list) > 10:
                available = ", ".join(available_list[:10]) + f" (and {len(available_list) - 10} more)"
            else:
                available = ", ".join(available_list) if available_list else "none"
        else:
            available = "none"
        return (
            f"Error: Thread '{topic}' not found in {threads_dir}\n\nAvailable threads: {available}",
            [],
        )

    content = fs.read_body(thread_path)
    entries = parse_thread_entries(content)
    return (None, entries)


def _entry_header_payload(entry: ThreadEntry) -> Dict[str, object]:
    return {
        "index": entry.index,
        "entry_id": entry.entry_id,
        "agent": entry.agent,
        "timestamp": entry.timestamp,
        "role": entry.role,
        "type": entry.entry_type,
        "title": entry.title,
        "header": entry.header,
        "start_line": entry.start_line,
        "end_line": entry.end_line,
        "start_offset": entry.start_offset,
        "end_offset": entry.end_offset,
    }


def _entry_full_payload(entry: ThreadEntry) -> Dict[str, object]:
    """Convert ThreadEntry to full JSON payload including body content.

    Note on whitespace handling:
        - 'body' field preserves original whitespace from the thread file
        - 'markdown' field uses stripped body to avoid trailing whitespace in output
        This ensures markdown rendering is clean while preserving original content.

    Args:
        entry: ThreadEntry to convert

    Returns:
        Dictionary with entry metadata, body, and markdown representation
    """
    data = _entry_header_payload(entry)
    # Handle whitespace-only bodies as empty
    body_content = entry.body.strip() if entry.body else ""
    data.update(
        {
            "body": entry.body,  # Preserve original whitespace
            "markdown": entry.header + ("\n\n" + body_content if body_content else ""),  # Clean output
        }
    )
    return data


def _validate_thread_context(code_path: str) -> tuple[str | None, ThreadContext | None]:
    """Validate and resolve thread context for MCP tools.

    Args:
        code_path: Path to code repository

    Returns:
        Tuple of (error_message, context). If error_message is not None, context will be None.
    """
    error, context = _require_context(code_path)
    if error:
        return (error, None)
    if context is None:
        return ("Error: Unable to resolve code context for the provided code_path.", None)
    if _dynamic_context_missing(context):
        return (
            "Dynamic threads repo was not resolved from your git context.\n"
            "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO.",
            None,
        )
    return (None, context)


def _build_commit_footers(
    context: ThreadContext,
    *,
    topic: str | None = None,
    entry_id: str | None = None,
    agent_spec: str | None = None,
) -> list[str]:
    footers: list[str] = []
    if entry_id:
        footers.append(f"Watercooler-Entry-ID: {entry_id}")
    if topic:
        footers.append(f"Watercooler-Topic: {topic}")
    if context.code_repo:
        footers.append(f"Code-Repo: {context.code_repo}")
    if context.code_branch:
        footers.append(f"Code-Branch: {context.code_branch}")
    if context.code_commit:
        footers.append(f"Code-Commit: {context.code_commit}")
    if agent_spec:
        footers.append(f"Spec: {agent_spec}")
    return footers


def run_with_sync(
    context: ThreadContext,
    commit_title: str,
    operation: Callable[[], T],
    *,
    topic: str | None = None,
    entry_id: str | None = None,
    agent_spec: str | None = None,
    priority_flush: bool = False,
    skip_validation: bool = False,
) -> T:
    sync = get_git_sync_manager_from_context(context)
    if not sync:
        return operation()

    # Validate and sync branches before write operation
    _validate_and_sync_branches(context, skip_validation=skip_validation)

    footers = _build_commit_footers(
        context,
        topic=topic,
        entry_id=entry_id,
        agent_spec=agent_spec,
    )
    commit_message = commit_title if not footers else f"{commit_title}\n\n" + "\n".join(footers)
    return sync.with_sync(
        operation,
        commit_message,
        topic=topic,
        entry_id=entry_id,
        priority_flush=priority_flush,
    )


# ============================================================================
# Resources (Instructions & Documentation)
# ============================================================================

@mcp.resource("watercooler://instructions")
def get_instructions() -> str:
    """Get comprehensive instructions for using watercooler effectively.

    This resource provides quick-start guidance, common workflows, and best
    practices for AI agents collaborating via watercooler threads.
    """
    return f"""# Watercooler Cloud Guide for AI Agents

## 🎯 Quick Start

The simplest way to collaborate:

```bash
watercooler say <topic> --title "Your title" --body "Your message"
```

This ONE command:
- Creates the thread if it doesn't exist
- Adds your entry with timestamp and attribution
- Automatically flips the ball to your counterpart
- Returns you to async work

## 📋 Common Workflows

### Starting a New Discussion
```bash
watercooler say feature-auth --title "Authentication design" --body "Proposing OAuth2 with JWT tokens..."
```

### Responding to a Thread
```bash
# First, see what's new
watercooler list

# Read the full thread
watercooler say <topic> --title "Response" --body "Agreed, let's proceed..."
```

### Acknowledging Without Taking Action
```bash
watercooler ack <topic> --title "Noted" --body "Thanks, looks good!"
```

### Handing Off to Someone Specific
```bash
watercooler handoff <topic> "Ready for review" --target Claude
```

### Updating Thread Status
```bash
watercooler set-status <topic> IN_REVIEW
watercooler set-status <topic> CLOSED
```

## 🎾 The Ball Pattern

The **ball** indicates whose turn it is:
- When you `say`, the ball flips to your counterpart automatically
- When you `ack`, the ball stays where it is
- When you `handoff`, you explicitly pass the ball

## 💡 Best Practices

1. **Be Specific** - Use descriptive topic names (feature-auth, bug-login, refactor-api)
2. **Stay Focused** - One thread per topic/decision
3. **Mark NEW threads** - The `list` command shows NEW entries you haven't seen
4. **Close When Done** - Use `set-status <topic> CLOSED` when resolved
5. **Keep it Async** - Don't wait for responses, move on to other work

## 🔧 Available Tools (MCP)

- `watercooler_v1_list_threads` - See all threads, identify where you have the ball
- `watercooler_v1_read_thread` - Read full thread content
- `watercooler_v1_say` - Add entry and flip ball (most common)
- `watercooler_v1_ack` - Acknowledge without flipping ball
- `watercooler_v1_handoff` - Explicitly hand off to another agent
- `watercooler_v1_set_status` - Update thread status
- `watercooler_v1_reindex` - Generate summary of all threads
- `watercooler_v1_health` - Check server status
- `watercooler_v1_whoami` - Check your agent identity

## 🚀 Pro Tips

- Thread topics use kebab-case (feature-auth, not "Feature Auth")
- Titles should be brief summaries (1-5 words)
- Bodies support full markdown formatting
- You can pass `--role` (planner/implementer/tester/pm/critic/scribe)
- You can pass `--type` (Note/Plan/Decision/PR/Closure)

---
*Generated by Watercooler MCP Server v{get_version()}*
"""


# ============================================================================
# Diagnostic Tools (Phase 1A)
# ============================================================================

@mcp.tool(name="watercooler_v1_health")
def health(ctx: Context) -> str:
    """Check server health and configuration.

    Returns server version, configured agent identity, and threads directory.
    Useful for debugging configuration issues.

    Example output:
        Watercooler MCP Server v0.1.0
        Status: Healthy
        Agent: Codex
        Threads Dir: /path/to/project/.watercooler
        Threads Dir Exists: True
    """
    try:
        agent = get_agent_name(ctx.client_id)
        context = resolve_thread_context()
        threads_dir = context.threads_dir
        version = get_version()

        # Create threads directory if it doesn't exist
        if not threads_dir.exists():
            threads_dir.mkdir(parents=True, exist_ok=True)

        # Lightweight diagnostics to help average users verify env
        py_exec = sys.executable or "unknown"
        try:
            import fastmcp as _fm
            fm_ver = getattr(_fm, "__version__", "unknown")
        except Exception:
            fm_ver = "not-importable"

        status = (
            f"Watercooler MCP Server v{version}\n"
            f"Status: Healthy\n"
            f"Agent: {agent}\n"
            f"Threads Dir: {threads_dir}\n"
            f"Threads Dir Exists: {threads_dir.exists()}\n"
            f"Threads Repo URL: {context.threads_repo_url or 'local-only'}\n"
            f"Code Branch: {context.code_branch or 'n/a'}\n"
            f"Auto-Branch: {'enabled' if _should_auto_branch() else 'disabled'}\n"
            f"Python: {py_exec}\n"
            f"fastmcp: {fm_ver}\n"
        )
        return status
    except Exception as e:
        return f"Watercooler MCP Server\nStatus: Error\nError: {str(e)}"


@mcp.tool(name="watercooler_v1_whoami")
def whoami(ctx: Context) -> str:
    """Get your resolved agent identity.

    Returns the agent name that will be used when you create entries.
    Automatically detects your identity from the MCP client.

    Example:
        You are: Claude
    """
    try:
        agent = get_agent_name(ctx.client_id)
        debug_info = f"\nClient ID: {ctx.client_id or 'None'}\nSession ID: {ctx.session_id or 'None'}"
        return f"You are: {agent}{debug_info}"
    except Exception as e:
        return f"Error determining identity: {str(e)}"


# ============================================================================
# Core Tools (Phase 1A)
# ============================================================================

@mcp.tool(name="watercooler_v1_list_threads")
def list_threads(
    ctx: Context,
    open_only: bool | None = None,
    limit: int = 50,
    cursor: str | None = None,
    format: str = "markdown",
    code_path: str = "",
) -> ToolResult:
    """List all watercooler threads.

    Shows threads where you have the ball (actionable items), threads where
    you're waiting on others, and marks NEW entries since you last contributed.

    Args:
        open_only: Filter by open status (True=open only, False=closed only, None=all)
        limit: Maximum threads to return (Phase 1A: ignored, returns all)
        cursor: Pagination cursor (Phase 1A: ignored, no pagination)
        format: Output format - "markdown" or "json" (Phase 1A: only "markdown" supported)
        code_path: Path to the code repository directory containing the files most immediately 
            under discussion. This establishes the code context for branch pairing. 
            Should point to the root of your working repository.

    Returns:
        Formatted thread list with:
        - Threads where you have the ball (🎾 marker)
        - Threads with NEW entries for you to read
        - Thread status and last update time

    Phase 1A notes:
        - format must be "markdown" (JSON support in Phase 1B)
        - limit and cursor are ignored (pagination in Phase 1B)
    """
    try:
        start_ts = time.time()
        if format != "markdown":
            return ToolResult(content=[TextContent(type="text", text=f"Error: Phase 1A only supports format='markdown'. JSON support coming in Phase 1B.")])

        error, context = _require_context(code_path)
        if error:
            return ToolResult(content=[TextContent(type="text", text=error)])
        if context is None:
            return ToolResult(content=[TextContent(type="text", text="Error: Unable to resolve code context for the provided code_path.")])
        log_debug(f"list_threads start code_path={code_path!r} open_only={open_only}")
        if context and _dynamic_context_missing(context):
            log_debug("list_threads dynamic context missing")
            return ToolResult(content=[TextContent(type="text", text=(
                "Dynamic threads repo was not resolved from your git context.\n"
                "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO on the MCP server.\n"
                f"Resolved threads dir: {context.threads_dir} (local fallback).\n"
                f"Code root: {context.code_root or Path.cwd()}"
            ))])

        agent = get_agent_name(ctx.client_id)
        log_debug("list_threads refreshing git state")
        git_start = time.time()
        _refresh_threads(context)
        git_elapsed = time.time() - git_start
        log_debug(f"list_threads git refreshed in {git_elapsed:.2f}s")
        threads_dir = context.threads_dir

        # Create threads directory if it doesn't exist
        if not threads_dir.exists():
            threads_dir.mkdir(parents=True, exist_ok=True)
            log_debug("list_threads created empty threads directory")
            return ToolResult(content=[TextContent(type="text", text=f"No threads found. Threads directory created at: {threads_dir}\n\nCreate your first thread with watercooler_v1_say.")])

        # Get thread list from commands module
        scan_start = time.time()
        threads = commands.list_threads(threads_dir=threads_dir, open_only=open_only)
        scan_elapsed = time.time() - scan_start
        log_debug(f"list_threads scanned {len(threads)} threads in {scan_elapsed:.2f}s")

        sync = get_git_sync_manager_from_context(context)
        pending_topics: set[str] = set()
        async_summary = ""
        if sync:
            status_info = sync.get_async_status()
            if status_info.get("mode") == "async":
                pending_topics = {topic for topic in (status_info.get("pending_topics") or []) if topic}
                summary_parts: list[str] = []
                if status_info.get("is_syncing"):
                    summary_parts.append("syncing…")
                last_pull_age = status_info.get("last_pull_age_seconds")
                if status_info.get("last_pull"):
                    age_fragment = f"{int(last_pull_age)}s ago" if last_pull_age is not None else "recently"
                    if status_info.get("stale"):
                        age_fragment += " (stale)"
                    summary_parts.append(f"last refresh {age_fragment}")
                else:
                    summary_parts.append("no refresh yet")
                next_eta = status_info.get("next_pull_eta_seconds")
                if next_eta is not None:
                    summary_parts.append(f"next sync in {int(next_eta)}s")
                summary_parts.append(f"pending {status_info.get('pending', 0)}")
                async_summary = "*Async sync: " + ", ".join(summary_parts) + "*\n"

        if not threads:
            status_filter = "open " if open_only is True else ("closed " if open_only is False else "")
            log_debug(f"list_threads no {status_filter or ''}threads found")
            return ToolResult(content=[TextContent(type="text", text=f"No {status_filter}threads found in: {threads_dir}")])

        # Format output
        agent_lower = agent.lower()
        output = []
        output.append(f"# Watercooler Threads ({len(threads)} total)\n")
        if async_summary:
            output.append(async_summary)

        # Separate threads by ball ownership
        classify_start = time.time()
        your_turn = []
        waiting = []
        new_entries = []

        for title, status, ball, updated, path, is_new in threads:
            topic = path.stem
            ball_lower = (ball or "").lower()
            has_ball = ball_lower == agent_lower

            if is_new:
                new_entries.append((title, status, ball, updated, topic, has_ball))
            elif has_ball:
                your_turn.append((title, status, ball, updated, topic, has_ball))
            else:
                waiting.append((title, status, ball, updated, topic, has_ball))
        classify_elapsed = time.time() - classify_start
        log_debug(f"list_threads classified threads in {classify_elapsed:.2f}s (your_turn={len(your_turn)} waiting={len(waiting)} new={len(new_entries)})")

        # Your turn section
        render_start = time.time()
        if your_turn:
            output.append(f"\n## 🎾 Your Turn ({len(your_turn)} threads)\n")
            for title, status, ball, updated, topic, _ in your_turn:
                local_marker = " ⏳" if topic in pending_topics else ""
                updated_label = updated + (" (local)" if topic in pending_topics else "")
                output.append(f"- **{topic}**{local_marker} - {title}")
                output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated_label}")

        # NEW entries section
        if new_entries:
            output.append(f"\n## 🆕 NEW Entries for You ({len(new_entries)} threads)\n")
            for title, status, ball, updated, topic, has_ball in new_entries:
                marker = "🎾 " if has_ball else ""
                local_marker = " ⏳" if topic in pending_topics else ""
                updated_label = updated + (" (local)" if topic in pending_topics else "")
                output.append(f"- {marker}**{topic}**{local_marker} - {title}")
                output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated_label}")

        # Waiting section
        if waiting:
            output.append(f"\n## ⏳ Waiting on Others ({len(waiting)} threads)\n")
            for title, status, ball, updated, topic, _ in waiting:
                local_marker = " ⏳" if topic in pending_topics else ""
                updated_label = updated + (" (local)" if topic in pending_topics else "")
                output.append(f"- **{topic}**{local_marker} - {title}")
                output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated_label}")

        output.append(f"\n---\n*You are: {agent}*")
        output.append(f"*Threads dir: {threads_dir}*")

        response = "\n".join(output)
        render_elapsed = time.time() - render_start
        log_debug(f"list_threads rendered markdown sections in {render_elapsed:.2f}s")
        duration = time.time() - start_ts
        log_debug(
            f"list_threads formatted response in "
            f"{duration:.2f}s (total={len(threads)} new={len(new_entries)} "
            f"your_turn={len(your_turn)} waiting={len(waiting)} "
            f"chars={len(response)})"
        )
        log_debug("list_threads returning response")
        return ToolResult(content=[TextContent(type="text", text=response)])

    except Exception as e:
        log_error(f"list_threads error: {e}")
        return ToolResult(content=[TextContent(type="text", text=f"Error listing threads: {str(e)}")])


@mcp.tool(name="watercooler_v1_read_thread")
def read_thread(
    topic: str,
    from_entry: int = 0,
    limit: int = 100,
    format: str = "markdown",
    code_path: str = "",
) -> str:
    """Read the complete content of a watercooler thread.

    Args:
        topic: Thread topic identifier (e.g., "feature-auth")
        from_entry: Starting entry index for pagination (Phase 1A: ignored)
        limit: Maximum entries to include (Phase 1A: ignored, returns all)
        format: Output format - "markdown" or "json" (Phase 1A: only "markdown" supported)
        code_path: Path to the code repository directory containing the files most immediately 
            under discussion. This establishes the code context for branch pairing. 
            Should point to the root of your working repository.

    Returns:
        Full thread content including:
        - Thread metadata (status, ball owner, participants)
        - All entries with timestamps, authors, roles, and types
        - Current ball ownership status

    Phase 1A notes:
        - format must be "markdown" (JSON support in Phase 1B)
        - from_entry and limit are ignored (pagination in Phase 1B)
    """
    try:
        fmt_error, resolved_format = _resolve_format(format, default="markdown")
        if fmt_error:
            return fmt_error

        error, context = _require_context(code_path)
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."

        if _dynamic_context_missing(context):
            return (
                "Dynamic threads repo was not resolved from your git context.\n"
                "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO."
            )

        _refresh_threads(context)
        threads_dir = context.threads_dir

        # Create threads directory if it doesn't exist
        if not threads_dir.exists():
            threads_dir.mkdir(parents=True, exist_ok=True)

        thread_path = fs.thread_path(topic, threads_dir)

        if not thread_path.exists():
            return f"Error: Thread '{topic}' not found in {threads_dir}\n\nAvailable threads: {', '.join(p.stem for p in threads_dir.glob('*.md')) if threads_dir.exists() else 'none'}"

        # Read full thread content
        content = fs.read_body(thread_path)
        if resolved_format == "markdown":
            return content

        # Parse once and extract all needed data from content
        entries = parse_thread_entries(content)
        header_block = content.split("---", 1)[0].strip() if "---" in content else ""
        title, status, ball, last = _extract_thread_metadata(content, topic)

        payload = {
            "topic": topic,
            "format": "json",
            "entry_count": len(entries),
            "meta": {
                "title": title,
                "status": status,
                "ball": ball,
                "last_entry_at": last,
                "header": header_block,
            },
            "entries": [_entry_full_payload(entry) for entry in entries],
        }
        return json.dumps(payload, indent=2)

    except Exception as e:
        return f"Error reading thread '{topic}': {str(e)}"


@mcp.tool(name="watercooler_v1_list_thread_entries")
def list_thread_entries(
    topic: str,
    offset: int = 0,
    limit: int | None = None,
    format: str = "json",
    code_path: str = "",
) -> ToolResult:
    """Return thread entry headers (metadata only) with optional pagination."""

    fmt_error, resolved_format = _resolve_format(format, default="json")
    if fmt_error:
        return ToolResult(content=[TextContent(type="text", text=fmt_error)])

    error, context = _validate_thread_context(code_path)
    if error or context is None:
        return ToolResult(content=[TextContent(type="text", text=error or "Unknown error")])

    if offset < 0:
        return ToolResult(content=[TextContent(type="text", text="Error: offset must be non-negative.")])
    if offset > _MAX_OFFSET:
        return ToolResult(content=[TextContent(type="text", text=f"Error: offset must not exceed {_MAX_OFFSET}.")])
    if limit is not None and limit < 0:
        return ToolResult(content=[TextContent(type="text", text="Error: limit must be non-negative when provided.")])
    if limit is not None and limit > _MAX_LIMIT:
        return ToolResult(content=[TextContent(type="text", text=f"Error: limit must not exceed {_MAX_LIMIT}.")])

    _refresh_threads(context)
    load_error, entries = _load_thread_entries(topic, context)
    if load_error:
        return ToolResult(content=[TextContent(type="text", text=load_error)])

    total = len(entries)
    start = min(offset, total)
    end = total if limit is None else min(start + limit, total)
    slice_entries = entries[start:end]

    payload = {
        "topic": topic,
        "entry_count": total,
        "offset": start,
        "limit": limit,
        "entries": [_entry_header_payload(entry) for entry in slice_entries],
    }

    if resolved_format == "markdown":
        lines = [f"Entries for '{topic}' ({total} total)"]
        if slice_entries:
            for entry in slice_entries:
                timestamp = entry.timestamp or "unknown"
                title = entry.title or "(untitled)"
                entry_id = entry.entry_id or "(no Entry-ID)"
                lines.append(
                    f"- [{entry.index}] {timestamp} — {title} ({entry.role or 'role?'} / {entry.entry_type or 'type?'}) id={entry_id}"
                )
        else:
            lines.append("- (no entries in range)")
        text = "\n".join(lines)
        return ToolResult(content=[TextContent(type="text", text=text)])

    return ToolResult(content=[TextContent(type="text", text=json.dumps(payload, indent=2))])


@mcp.tool(name="watercooler_v1_get_thread_entry")
def get_thread_entry(
    topic: str,
    index: int | None = None,
    entry_id: str | None = None,
    format: str = "json",
    code_path: str = "",
) -> ToolResult:
    """Return a single thread entry (header + body)."""

    fmt_error, resolved_format = _resolve_format(format, default="json")
    if fmt_error:
        return ToolResult(content=[TextContent(type="text", text=fmt_error)])

    if index is None and entry_id is None:
        return ToolResult(content=[TextContent(type="text", text="Error: provide either index or entry_id to select an entry.")])

    error, context = _validate_thread_context(code_path)
    if error or context is None:
        return ToolResult(content=[TextContent(type="text", text=error or "Unknown error")])

    _refresh_threads(context)
    load_error, entries = _load_thread_entries(topic, context)
    if load_error:
        return ToolResult(content=[TextContent(type="text", text=load_error)])

    selected: ThreadEntry | None = None

    if index is not None:
        if index < 0 or index >= len(entries):
            return ToolResult(content=[TextContent(type="text", text=f"Error: index {index} out of range (entries={len(entries)}).")])
        selected = entries[index]

    if entry_id is not None:
        matching = next((entry for entry in entries if entry.entry_id == entry_id), None)
        if matching is None:
            return ToolResult(content=[TextContent(type="text", text=f"Error: entry_id '{entry_id}' not found in thread '{topic}'.")])
        if selected is not None and matching.index != selected.index:
            return ToolResult(content=[TextContent(type="text", text="Error: index and entry_id refer to different entries.")])
        selected = matching

    if selected is None:
        return ToolResult(content=[TextContent(type="text", text="Error: failed to resolve the requested entry.")])

    payload = {
        "topic": topic,
        "entry_count": len(entries),
        "index": selected.index,
        "entry": _entry_full_payload(selected),
    }

    if resolved_format == "markdown":
        markdown = payload["entry"]["markdown"]  # type: ignore[index]
        return ToolResult(content=[TextContent(type="text", text=markdown)])

    return ToolResult(content=[TextContent(type="text", text=json.dumps(payload, indent=2))])


@mcp.tool(name="watercooler_v1_get_thread_entry_range")
def get_thread_entry_range(
    topic: str,
    start_index: int = 0,
    end_index: int | None = None,
    format: str = "json",
    code_path: str = "",
) -> ToolResult:
    """Return a contiguous range of entries (inclusive)."""

    fmt_error, resolved_format = _resolve_format(format, default="json")
    if fmt_error:
        return ToolResult(content=[TextContent(type="text", text=fmt_error)])

    if start_index < 0:
        return ToolResult(content=[TextContent(type="text", text="Error: start_index must be non-negative.")])
    if start_index > _MAX_OFFSET:
        return ToolResult(content=[TextContent(type="text", text=f"Error: start_index must not exceed {_MAX_OFFSET}.")])
    if end_index is not None and end_index < start_index:
        return ToolResult(content=[TextContent(type="text", text="Error: end_index must be greater than or equal to start_index.")])
    if end_index is not None and (end_index - start_index) > _MAX_LIMIT:
        return ToolResult(content=[TextContent(type="text", text=f"Error: requested range size must not exceed {_MAX_LIMIT} entries.")])

    error, context = _validate_thread_context(code_path)
    if error or context is None:
        return ToolResult(content=[TextContent(type="text", text=error or "Unknown error")])

    _refresh_threads(context)
    load_error, entries = _load_thread_entries(topic, context)
    if load_error:
        return ToolResult(content=[TextContent(type="text", text=load_error)])

    total = len(entries)
    if start_index >= total and total > 0:
        return ToolResult(content=[TextContent(type="text", text=f"Error: start_index {start_index} out of range (entries={total}).")])

    last_index = total - 1 if total else -1
    effective_end = last_index if end_index is None else min(end_index, last_index)
    if effective_end < start_index and total:
        return ToolResult(content=[TextContent(type="text", text="Error: computed end index is before start index.")])

    selected_entries = entries[start_index : effective_end + 1] if total else []

    payload = {
        "topic": topic,
        "entry_count": total,
        "start_index": start_index,
        "end_index": effective_end if selected_entries else None,
        "entries": [_entry_full_payload(entry) for entry in selected_entries],
    }

    if resolved_format == "markdown":
        if not selected_entries:
            return ToolResult(content=[TextContent(type="text", text="(no entries in range)")])
        markdown_blocks = []
        for entry in selected_entries:
            block = entry.header
            if entry.body:
                block += "\n\n" + entry.body
            markdown_blocks.append(block)
        text = "\n\n---\n\n".join(markdown_blocks)
        return ToolResult(content=[TextContent(type="text", text=text)])

    return ToolResult(content=[TextContent(type="text", text=json.dumps(payload, indent=2))])


@mcp.tool(name="watercooler_v1_say")
def say(
    topic: str,
    title: str,
    body: str,
    ctx: Context,
    role: str = "implementer",
    entry_type: str = "Note",
    create_if_missing: bool = False,
    code_path: str = "",
    agent_func: str = "",
) -> str:
    """Add your response to a thread and flip the ball to your counterpart.

    Use this when you want to contribute and pass the action to another agent.
    The ball automatically flips to your configured counterpart.

    Args:
        topic: Thread topic identifier (e.g., "feature-auth")
        title: Entry title - brief summary of your contribution
        body: Full entry content (markdown supported). In general, threads follow an arc:
            - Start: Persist the state of the project at the start, describe why the thread exists,
              and lay out the desired state change for the code/project
            - Middle: Reason towards the appropriate solution
            - End: Describe the effective solution reached
            - Often: Recap that arc in a closing message to the thread
            Thread entries should explicitly reference any files changed, using file paths
            (e.g., `src/watercooler_mcp/server.py`, `docs/README.md`) to maintain clear
            traceability of what was modified.
        role: Your role - planner, critic, implementer, tester, pm, or scribe (default: implementer)
        entry_type: Entry type - Note, Plan, Decision, PR, or Closure (default: Note)
        create_if_missing: Whether to create the thread if it doesn't exist (default: False, but threads are auto-created by commands.say)
        code_path: Path to the code repository directory containing the files most immediately 
            under discussion in this thread. This establishes the code context for branch pairing 
            and commit footers. Should point to the root of your working repository.
        agent_func: Agent identity in format '<platform>:<model>:<role>' where:
            - platform: The actual IDE/platform name (e.g., 'Cursor', 'Claude Code', 'Codex')
            - model: The exact model identifier as it identifies itself (e.g., 'Composer 1', 'sonnet-4', 'gpt-4')
            - role: The agent role (e.g., 'implementer', 'reviewer', 'planner')
            Full examples: 'Cursor:Composer 1:implementer', 'Claude Code:sonnet-4:reviewer', 'Codex:gpt-4:planner'
            This information is recorded in commit footers for full traceability.

    Returns:
        Confirmation message with updated ball status

    Example:
        say("feature-auth", "Implementation complete", "All tests passing. Ready for review.", 
            role="implementer", entry_type="Note", code_path="/path/to/repo", 
            agent_func="Cursor:Composer 1:implementer")
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."

        if not agent_func or ":" not in agent_func:
            return "identity required: pass agent_func as '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"

        threads_dir = context.threads_dir
        agent = agent_base or get_agent_name(ctx.client_id)

        # Generate unique Entry-ID for idempotency
        entry_id = str(ULID())

        # Define the append operation
        def append_operation():
            commands.say(
                topic,
                threads_dir=threads_dir,
                agent=agent,
                role=role,
                title=title,
                entry_type=entry_type,
                body=body,
                entry_id=entry_id,
            )

        run_with_sync(
            context,
            f"{agent}: {title} ({topic})",
            append_operation,
            topic=topic,
            entry_id=entry_id,
            agent_spec=agent_spec,
            priority_flush=True,
        )

        # Get updated thread meta to show new ball owner
        thread_path = fs.thread_path(topic, threads_dir)
        from watercooler.metadata import thread_meta
        _, status, ball, _ = thread_meta(thread_path)

        return (
            f"✅ Entry added to '{topic}'\n"
            f"Title: {title}\n"
            f"Role: {role} | Type: {entry_type}\n"
            f"Ball flipped to: {ball}\n"
            f"Status: {status}"
        )

    except Exception as e:
        return f"Error adding entry to '{topic}': {str(e)}"


@mcp.tool(name="watercooler_v1_ack")
def ack(
    topic: str,
    ctx: Context,
    title: str = "",
    body: str = "",
    code_path: str = "",
    agent_func: str = "",
) -> str:
    """Acknowledge a thread without flipping the ball.

    Use this when you've read updates but don't need to pass the action.
    The ball stays with the current owner.

    Args:
        topic: Thread topic identifier
        title: Optional acknowledgment title (default: "Ack")
        body: Optional acknowledgment message (default: "ack")
        code_path: Path to the code repository directory containing the files most immediately 
            under discussion in this thread. This establishes the code context for branch pairing 
            and commit footers. Should point to the root of your working repository.
        agent_func: Agent identity in format '<platform>:<model>:<role>' where:
            - platform: The actual IDE/platform name (e.g., 'Cursor', 'Claude Code', 'Codex')
            - model: The exact model identifier as it identifies itself (e.g., 'Composer 1', 'sonnet-4', 'gpt-4')
            - role: The agent role (e.g., 'implementer', 'reviewer', 'planner')
            Full examples: 'Cursor:Composer 1:implementer', 'Claude Code:sonnet-4:reviewer', 'Codex:gpt-4:planner'
            This information is recorded in commit footers for full traceability.

    Returns:
        Confirmation message

    Example:
        ack("feature-auth", "Noted", "Thanks for the update, looks good!", 
            code_path="/path/to/repo", agent_func="Claude Code:sonnet-4:reviewer")
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."
        if _dynamic_context_missing(context):
            return (
                "Dynamic threads repo was not resolved from your git context.\n"
                "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO."
            )

        if not agent_func or ":" not in agent_func:
            return "identity required: pass agent_func as '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"
        threads_dir = context.threads_dir
        agent = agent_base or get_agent_name(ctx.client_id)

        def ack_operation():
            commands.ack(
                topic,
                threads_dir=threads_dir,
                agent=agent,
                title=title or None,
                body=body or None,
            )

        run_with_sync(
            context,
            f"{agent}: {title or 'Ack'} ({topic})",
            ack_operation,
            topic=topic,
            agent_spec=agent_spec,
        )

        # Get updated thread meta
        thread_path = fs.thread_path(topic, threads_dir)
        from watercooler.metadata import thread_meta
        _, status, ball, _ = thread_meta(thread_path)

        ack_title = title or "Ack"
        return (
            f"✅ Acknowledged '{topic}'\n"
            f"Title: {ack_title}\n"
            f"Ball remains with: {ball}\n"
            f"Status: {status}"
        )

    except Exception as e:
        return f"Error acknowledging '{topic}': {str(e)}"


@mcp.tool(name="watercooler_v1_handoff")
def handoff(
    topic: str,
    ctx: Context,
    note: str = "",
    target_agent: str | None = None,
    code_path: str = "",
    agent_func: str = "",
) -> str:
    """Hand off the ball to another agent.

    If target_agent is None, hands off to your default counterpart.
    If target_agent is specified, explicitly hands off to that agent.

    Args:
        topic: Thread topic identifier
        note: Optional handoff message explaining context
        target_agent: Agent name to receive the ball (optional, uses counterpart if None)
        code_path: Path to the code repository directory containing the files most immediately 
            under discussion in this thread. This establishes the code context for branch pairing 
            and commit footers. Should point to the root of your working repository.
        agent_func: Agent identity in format '<platform>:<model>:<role>' where:
            - platform: The actual IDE/platform name (e.g., 'Cursor', 'Claude Code', 'Codex')
            - model: The exact model identifier as it identifies itself (e.g., 'Composer 1', 'sonnet-4', 'gpt-4')
            - role: The agent role (e.g., 'implementer', 'reviewer', 'planner')
            Full examples: 'Cursor:Composer 1:implementer', 'Claude Code:sonnet-4:reviewer', 'Codex:gpt-4:planner'
            This information is recorded in commit footers for full traceability.

    Returns:
        Confirmation with new ball owner

    Example:
        handoff("feature-auth", "Ready for your review", target_agent="Claude", 
                code_path="/path/to/repo", agent_func="Cursor:Composer 1:implementer")
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."
        if _dynamic_context_missing(context):
            return (
                "Dynamic threads repo was not resolved from your git context.\n"
                "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO."
            )

        if not agent_func or ":" not in agent_func:
            return "identity required: pass agent_func as '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"
        threads_dir = context.threads_dir
        agent = agent_base or get_agent_name(ctx.client_id)

        if target_agent:
            def op():
                commands.set_ball(topic, threads_dir=threads_dir, ball=target_agent)
                if note:
                    commands.append_entry(
                        topic,
                        threads_dir=threads_dir,
                        agent=agent,
                        role="pm",
                        title=f"Handoff to {target_agent}",
                        entry_type="Note",
                        body=note,
                        ball=target_agent,
                    )

            run_with_sync(
                context,
                f"{agent}: Handoff to {target_agent} ({topic})",
                op,
                topic=topic,
                agent_spec=agent_spec,
                priority_flush=True,
            )

            return (
                f"✅ Ball handed off to: {target_agent}\n"
                f"Thread: {topic}\n"
                + (f"Note: {note}" if note else "")
            )
        else:
            def op():
                commands.handoff(
                    topic,
                    threads_dir=threads_dir,
                    agent=agent,
                    note=note or None,
                )

            run_with_sync(
                context,
                f"{agent}: Handoff ({topic})",
                op,
                topic=topic,
                agent_spec=agent_spec,
                priority_flush=True,
            )

            # Get updated thread meta
            thread_path = fs.thread_path(topic, threads_dir)
            from watercooler.metadata import thread_meta
            _, status, ball, _ = thread_meta(thread_path)

            return (
                f"✅ Ball handed off to: {ball}\n"
                f"Thread: {topic}\n"
                f"Status: {status}\n"
                + (f"Note: {note}" if note else "")
            )

    except Exception as e:
        return f"Error handing off '{topic}': {str(e)}"


@mcp.tool(name="watercooler_v1_set_status")
def set_status(
    topic: str,
    status: str,
    code_path: str = "",
    agent_func: str = "",
) -> str:
    """Update the status of a thread.

    Common statuses: OPEN, IN_REVIEW, CLOSED, BLOCKED

    Args:
        topic: Thread topic identifier
        status: New status value (e.g., "IN_REVIEW", "CLOSED")
        code_path: Path to the code repository directory containing the files most immediately 
            under discussion in this thread. This establishes the code context for branch pairing 
            and commit footers. Should point to the root of your working repository.
        agent_func: Agent identity in format '<platform>:<model>:<role>' where:
            - platform: The actual IDE/platform name (e.g., 'Cursor', 'Claude Code', 'Codex')
            - model: The exact model identifier as it identifies itself (e.g., 'Composer 1', 'sonnet-4', 'gpt-4')
            - role: The agent role (e.g., 'implementer', 'reviewer', 'planner')
            Full examples: 'Cursor:Composer 1:implementer', 'Claude Code:sonnet-4:reviewer', 'Codex:gpt-4:planner'
            This information is recorded in commit footers for full traceability.

    Returns:
        Confirmation message

    Example:
        set_status("feature-auth", "IN_REVIEW", code_path="/path/to/repo", 
                   agent_func="Claude Code:sonnet-4:pm")
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."
        if _dynamic_context_missing(context):
            return (
                "Dynamic threads repo was not resolved from your git context.\n"
                "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO."
            )

        if not agent_func or ":" not in agent_func:
            return "identity required: pass agent_func as '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<platform>:<model>:<role>' (e.g., 'Cursor:Composer 1:implementer')"
        threads_dir = context.threads_dir

        def op():
            commands.set_status(topic, threads_dir=threads_dir, status=status)

        priority_flush = status.strip().upper() == "CLOSED"

        run_with_sync(
            context,
            f"{agent_base}: Status changed to {status} ({topic})",
            op,
            topic=topic,
            agent_spec=agent_spec,
            priority_flush=priority_flush,
        )

        return (
            f"✅ Status updated for '{topic}'\n"
            f"New status: {status}"
        )

    except Exception as e:
        return f"Error setting status for '{topic}': {str(e)}"


@mcp.tool(name="watercooler_v1_sync")
def force_sync(
    ctx: Context,
    code_path: str = "",
    action: str = "now",
) -> str:
    """Inspect or flush the async git sync worker.

    Args:
        action: Action to perform - "status"/"inspect" to view sync state, or "now"/"flush" to force immediate sync (default: "now")
        code_path: Path to the code repository directory. This establishes the code context for 
            determining which threads repository to sync. Should point to the root of your working repository.

    Returns:
        Status information or confirmation of sync operation
    """
    log_debug(f"TOOL_ENTRY: watercooler_v1_sync(code_path={code_path!r}, action={action!r})")
    try:
        log_debug("TOOL_STEP: calling _require_context")
        error, context = _require_context(code_path)
        log_debug(f"TOOL_STEP: _require_context returned (error={error!r}, context={'present' if context else 'None'})")
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."

        log_debug("TOOL_STEP: calling get_git_sync_manager_from_context")
        sync = get_git_sync_manager_from_context(context)
        log_debug(f"TOOL_STEP: get_git_sync_manager returned {'present' if sync else 'None'}")
        if not sync:
            return "Async sync unavailable: no git-enabled threads repository for this context."

        action_normalized = (action or "now").strip().lower()
        log_debug(f"TOOL_STEP: action_normalized={action_normalized!r}")

        def _format_status(info: dict) -> str:
            if info.get("mode") != "async":
                return "Async sync disabled; repository uses synchronous git writes."
            lines = ["Async sync status:"]
            lines.append(f"- Pending entries: {info.get('pending', 0)}")
            topics = info.get("pending_topics") or []
            if topics:
                lines.append(f"- Pending topics: {', '.join(topics)}")
            last_pull = info.get("last_pull")
            if last_pull:
                age = info.get("last_pull_age_seconds")
                age_fragment = f"{age:.1f}s ago" if age is not None else "recently"
                stale = " (stale)" if info.get("stale") else ""
                lines.append(f"- Last pull: {last_pull} ({age_fragment}){stale}")
            else:
                lines.append("- Last pull: never")
            next_eta = info.get("next_pull_eta_seconds")
            if next_eta is not None:
                lines.append(f"- Next background pull in: {next_eta:.1f}s")
            if info.get("is_syncing"):
                lines.append("- Sync in progress")
            if info.get("priority"):
                lines.append("- Priority flush requested")
            if info.get("retry_at"):
                retry_in = info.get("retry_in_seconds")
                extra = f" (in {retry_in:.1f}s)" if retry_in is not None else ""
                lines.append(f"- Next retry at: {info['retry_at']}{extra}")
            if info.get("last_error"):
                lines.append(f"- Last error: {info['last_error']}")
            return "\n".join(lines)

        if action_normalized in {"status", "inspect"}:
            log_debug("TOOL_STEP: calling sync.get_async_status()")
            status = sync.get_async_status()
            log_debug(f"TOOL_STEP: get_async_status returned {len(status)} keys")
            result = _format_status(status)
            log_debug(f"TOOL_STEP: formatted status, length={len(result)}")
            log_debug("TOOL_EXIT: returning status result")
            return result

        if action_normalized not in {"now", "flush"}:
            return f"Unknown action '{action}'. Use 'status' or 'now'."

        try:
            sync.flush_async()
        except GitPushError as exc:
            return f"Sync failed: {exc}"

        status_after = sync.get_async_status()
        remaining = status_after.get("pending", 0)
        prefix = "✅ Pending entries synced." if not remaining else f"⚠️ Sync completed with {remaining} entries still pending (retry scheduled)."
        return f"{prefix}\n\n{_format_status(status_after)}"

    except Exception as exc:  # pragma: no cover - defensive guard
        return f"Error running sync: {exc}"


@mcp.tool(name="watercooler_v1_reindex")
def reindex(ctx: Context) -> str:
    """Generate and return the index content summarizing all threads.

    Creates a summary view organized by:
    - Actionable threads (where you have the ball)
    - Open threads (waiting on others)
    - In Review threads
    - Closed threads are excluded by default

    Returns:
        Index content (Markdown) with links and status markers
    """
    try:
        threads_dir = get_threads_dir()
        agent = get_agent_name(ctx.client_id)

        # Create threads directory if it doesn't exist
        if not threads_dir.exists():
            threads_dir.mkdir(parents=True, exist_ok=True)
            return f"No threads found. Threads directory created at: {threads_dir}\n\nCreate your first thread with watercooler_v1_say."

        # Get all threads
        all_threads = commands.list_threads(threads_dir=threads_dir, open_only=None)

        if not all_threads:
            return f"No threads found in: {threads_dir}"

        # Categorize threads
        from watercooler.metadata import is_closed

        agent_lower = agent.lower()
        actionable = []
        in_review = []
        open_threads = []
        closed_threads = []

        for title, status, ball, updated, path, is_new in all_threads:
            topic = path.stem
            ball_lower = (ball or "").lower()
            has_ball = ball_lower == agent_lower

            if is_closed(status):
                closed_threads.append((topic, title, status, ball, updated, is_new))
            elif status.upper() == "IN_REVIEW":
                in_review.append((topic, title, status, ball, updated, is_new, has_ball))
            elif has_ball:
                actionable.append((topic, title, status, ball, updated, is_new))
            else:
                open_threads.append((topic, title, status, ball, updated, is_new))

        # Build index
        output = []
        output.append("# Watercooler Index\n")
        output.append(f"*Generated for: {agent}*\n")
        output.append(f"*Total threads: {len(all_threads)}*\n")

        if actionable:
            output.append(f"\n## 🎾 Actionable - Your Turn ({len(actionable)})\n")
            for topic, title, status, ball, updated, is_new in actionable:
                new_marker = " 🆕" if is_new else ""
                output.append(f"- [{topic}]({topic}.md){new_marker} - {title}")
                output.append(f"  *{status} | Updated: {updated}*")

        if open_threads:
            output.append(f"\n## ⏳ Open - Waiting on Others ({len(open_threads)})\n")
            for topic, title, status, ball, updated, is_new in open_threads:
                new_marker = " 🆕" if is_new else ""
                output.append(f"- [{topic}]({topic}.md){new_marker} - {title}")
                output.append(f"  *{status} | Ball: {ball} | Updated: {updated}*")

        if in_review:
            output.append(f"\n## 🔍 In Review ({len(in_review)})\n")
            for topic, title, status, ball, updated, is_new, has_ball in in_review:
                new_marker = " 🆕" if is_new else ""
                your_turn = " 🎾" if has_ball else ""
                output.append(f"- [{topic}]({topic}.md){new_marker}{your_turn} - {title}")
                output.append(f"  *{status} | Ball: {ball} | Updated: {updated}*")

        if closed_threads:
            output.append(f"\n## ✅ Closed ({len(closed_threads)})\n")
            for topic, title, status, ball, updated, is_new in closed_threads[:10]:  # Limit to 10
                output.append(f"- [{topic}]({topic}.md) - {title}")
                output.append(f"  *{status} | Updated: {updated}*")
            if len(closed_threads) > 10:
                output.append(f"\n*... and {len(closed_threads) - 10} more closed threads*")

        output.append(f"\n---\n*Threads directory: {threads_dir}*")

        return "\n".join(output)

    except Exception as e:
        return f"Error generating index: {str(e)}"


# ============================================================================
# Branch Sync Enforcement Tools
# ============================================================================

@mcp.tool(name="watercooler_v1_validate_branch_pairing")
def validate_branch_pairing_tool(
    ctx: Context,
    code_path: str = "",
    strict: bool = True,
) -> ToolResult:
    """Validate branch pairing between code and threads repos.

    Checks that the code repo and threads repo are on matching branches.
    This validation is automatically performed before all write operations,
    but this tool allows explicit checking.

    Args:
        code_path: Path to code repository directory. Defaults to current directory.
        strict: If True, return valid=False on any mismatch. If False, only return
                valid=False on critical errors.

    Returns:
        JSON result with validation status, branch names, mismatches, and warnings.
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return ToolResult(content=[TextContent(type="text", text=error)])
        if context is None or not context.code_root or not context.threads_dir:
            return ToolResult(content=[TextContent(
                type="text",
                text="Error: Unable to resolve code and threads repo paths."
            )])

        result = validate_branch_pairing(
            code_repo=context.code_root,
            threads_repo=context.threads_dir,
            strict=strict,
        )

        # Convert to JSON-serializable format
        output = {
            "valid": result.valid,
            "code_branch": result.code_branch,
            "threads_branch": result.threads_branch,
            "mismatches": [
                {
                    "type": m.type,
                    "code": m.code,
                    "threads": m.threads,
                    "severity": m.severity,
                    "recovery": m.recovery,
                }
                for m in result.mismatches
            ],
            "warnings": result.warnings,
        }

        return ToolResult(content=[TextContent(
            type="text",
            text=json.dumps(output, indent=2)
        )])

    except Exception as e:
        return ToolResult(content=[TextContent(
            type="text",
            text=f"Error validating branch pairing: {str(e)}"
        )])


@mcp.tool(name="watercooler_v1_sync_branch_state")
def sync_branch_state(
    ctx: Context,
    code_path: str = "",
    branch: Optional[str] = None,
    operation: str = "checkout",
    force: bool = False,
) -> ToolResult:
    """Synchronize branch state between code and threads repos.

    Performs branch lifecycle operations to keep repos in sync:
    - create: Create threads branch if code branch exists
    - delete: Delete threads branch if code branch deleted (with safeguards)
    - merge: Merge threads branch to main if code branch merged
    - checkout: Ensure both repos on same branch
    - recover: Recover from branch history divergence (e.g., after rebase/force-push)

    Note:
        This operational tool does **not** require ``agent_func`` or other
        provenance parameters. Unlike write operations (``watercooler_v1_say``,
        ``watercooler_v1_ack``, etc.), it only performs git lifecycle
        management, so pass just ``code_path``, ``branch``, ``operation``, and
        ``force``. FastMCP will automatically reject any unexpected parameters.

    Args:
        code_path: Path to code repository directory (default: current directory)
        branch: Specific branch to sync (default: current branch)
        operation: One of "create", "delete", "merge", "checkout", "recover" (default: "checkout")
        force: Skip safety checks (use with caution, default: False). For "recover",
               this controls whether to force-push after rebasing.

    Returns:
        Operation result with success/failure and any warnings.

    Example:
        >>> sync_branch_state(ctx, code_path=".", branch="feature-auth", operation="checkout")
        >>> sync_branch_state(ctx, code_path=".", branch="staging", operation="recover", force=True)
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return ToolResult(content=[TextContent(type="text", text=error)])
        if context is None or not context.code_root or not context.threads_dir:
            return ToolResult(content=[TextContent(
                type="text",
                text="Error: Unable to resolve code and threads repo paths."
            )])

        code_repo = Repo(context.code_root, search_parent_directories=True)
        threads_repo = Repo(context.threads_dir, search_parent_directories=True)

        target_branch = branch or context.code_branch
        if not target_branch:
            return ToolResult(content=[TextContent(
                type="text",
                text="Error: No branch specified and unable to detect current branch."
            )])

        warnings: List[str] = []
        result_msg = ""

        if operation == "checkout":
            # Ensure both repos on same branch
            if target_branch not in [b.name for b in code_repo.heads]:
                return ToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Branch '{target_branch}' does not exist in code repo."
                )])

            # Checkout code branch
            if code_repo.active_branch.name != target_branch:
                code_repo.git.checkout(target_branch)
                result_msg += f"Checked out '{target_branch}' in code repo.\n"

            # Checkout or create threads branch
            if target_branch in [b.name for b in threads_repo.heads]:
                if threads_repo.active_branch.name != target_branch:
                    threads_repo.git.checkout(target_branch)
                    result_msg += f"Checked out '{target_branch}' in threads repo.\n"
            else:
                # Create threads branch
                threads_repo.git.checkout('-b', target_branch)
                result_msg += f"Created and checked out '{target_branch}' in threads repo.\n"

            result_msg += f"✅ Both repos now on branch '{target_branch}'"

        elif operation == "create":
            # Create threads branch if code branch exists
            if target_branch not in [b.name for b in code_repo.heads]:
                return ToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Branch '{target_branch}' does not exist in code repo."
                )])

            if target_branch in [b.name for b in threads_repo.heads]:
                result_msg = f"Branch '{target_branch}' already exists in threads repo."
            else:
                threads_repo.git.checkout('-b', target_branch)
                result_msg = f"✅ Created branch '{target_branch}' in threads repo."

        elif operation == "delete":
            # Delete threads branch (with safeguards)
            if target_branch not in [b.name for b in threads_repo.heads]:
                return ToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Branch '{target_branch}' does not exist in threads repo."
                )])

            # Check for OPEN threads
            if not force:
                threads_repo.git.checkout(target_branch)
                threads_dir = context.threads_dir
                open_threads = []
                for thread_file in threads_dir.glob("*.md"):
                    try:
                        from watercooler.metadata import thread_meta, is_closed
                        title, status, ball, updated = thread_meta(thread_file)
                        if not is_closed(status):
                            open_threads.append(thread_file.stem)
                    except Exception:
                        pass

                if open_threads:
                    return ToolResult(content=[TextContent(
                        type="text",
                        text=(
                            f"Error: Cannot delete branch '{target_branch}' with OPEN threads:\n"
                            f"  {', '.join(open_threads)}\n"
                            f"Close threads first or use force=True to override."
                        )
                    )])

            # Switch to another branch before deleting
            if threads_repo.active_branch.name == target_branch:
                if "main" in [b.name for b in threads_repo.heads]:
                    threads_repo.git.checkout("main")
                else:
                    # Create main if it doesn't exist
                    threads_repo.git.checkout('-b', 'main')

            threads_repo.git.branch('-D', target_branch)
            result_msg = f"✅ Deleted branch '{target_branch}' from threads repo."

        elif operation == "merge":
            # Merge threads branch to main
            if target_branch not in [b.name for b in threads_repo.heads]:
                return ToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Branch '{target_branch}' does not exist in threads repo."
                )])

            if "main" not in [b.name for b in threads_repo.heads]:
                return ToolResult(content=[TextContent(
                    type="text",
                    text="Error: 'main' branch does not exist in threads repo."
                )])

            # Check for OPEN threads before merge
            if not force:
                threads_repo.git.checkout(target_branch)
                from watercooler.metadata import thread_meta, is_closed
                open_threads = []
                for thread_file in context.threads_dir.glob("*.md"):
                    try:
                        title, status, ball, updated = thread_meta(thread_file)
                        if not is_closed(status):
                            open_threads.append(thread_file.stem)
                    except Exception:
                        pass

                if open_threads:
                    warnings.append(f"Warning: {len(open_threads)} OPEN threads found on {target_branch}: {', '.join(open_threads)}")
                    warnings.append("Consider closing threads before merge or use force=True to proceed")

            # Detect squash merge in code repo
            squash_info = None
            if context.code_root:
                try:
                    from watercooler_mcp.git_sync import _detect_squash_merge
                    code_repo_obj = Repo(context.code_root, search_parent_directories=True)
                    is_squash, squash_sha = _detect_squash_merge(code_repo_obj, target_branch)
                    if is_squash:
                        squash_info = f"Detected squash merge in code repo"
                        if squash_sha:
                            squash_info += f" (squash commit: {squash_sha})"
                        warnings.append(squash_info)
                        warnings.append("Note: Original commits preserved in threads branch history")
                except Exception:
                    pass  # Ignore squash detection errors

            threads_repo.git.checkout("main")
            try:
                threads_repo.git.merge(target_branch, '--no-ff', '-m', f"Merge {target_branch} into main")

                # Check if code repo branch exists on remote - if yes, push threads merge too
                code_branch_on_remote = False
                if context.code_root:
                    try:
                        code_repo_obj = Repo(context.code_root, search_parent_directories=True)
                        remote_refs = [ref.name for ref in code_repo_obj.remote().refs]
                        code_branch_on_remote = f"origin/{target_branch}" in remote_refs
                    except Exception:
                        pass  # Ignore errors checking remote

                if code_branch_on_remote:
                    # Code branch is on remote, push threads merge too
                    threads_repo.git.push('origin', 'main')
                    result_msg = f"✅ Merged '{target_branch}' into 'main' in threads repo and pushed to remote."
                else:
                    # Code branch is local only, keep threads merge local
                    result_msg = f"✅ Merged '{target_branch}' into 'main' in threads repo (local only - code branch not on remote)."

                if warnings:
                    result_msg += "\n" + "\n".join(warnings)
            except GitCommandError as e:
                error_str = str(e)
                # Check if this is a merge conflict
                if "CONFLICT" in error_str or threads_repo.is_dirty():
                    # Detect conflicts in thread files
                    conflicted_files = []
                    for item in threads_repo.index.unmerged_blobs():
                        conflicted_files.append(item.path)
                    
                    if conflicted_files:
                        conflict_msg = (
                            f"Merge conflict detected in {len(conflicted_files)} file(s):\n"
                            f"  {', '.join(conflicted_files)}\n\n"
                            f"Append-only conflict resolution:\n"
                            f"  - Both entries will be preserved in chronological order\n"
                            f"  - Status/Ball conflicts: Higher severity status wins, last entry author gets ball\n"
                            f"  - Manual resolution may be required for complex conflicts\n\n"
                            f"To resolve:\n"
                            f"  1. Review conflicted files\n"
                            f"  2. Keep both entries in chronological order\n"
                            f"  3. Resolve header conflicts (status/ball) manually\n"
                            f"  4. Run: git add <files> && git commit"
                        )
                        warnings.append(conflict_msg)
                        return ToolResult(content=[TextContent(
                            type="text",
                            text=f"Merge conflict: {error_str}\n\n{conflict_msg}"
                        )])
                
                return ToolResult(content=[TextContent(
                    type="text",
                    text=f"Error merging branch: {error_str}"
                )])

        elif operation == "recover":
            # Recover from branch history divergence
            # This handles cases where threads branch has diverged from remote
            # (e.g., after force-push or rebase on code repo)

            if target_branch not in [b.name for b in threads_repo.heads]:
                return ToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Branch '{target_branch}' does not exist in threads repo."
                )])

            # Use sync_branch_history to attempt automatic recovery
            sync_result = sync_branch_history(
                threads_repo_path=context.threads_dir,
                branch=target_branch,
                strategy="rebase",  # Default to rebase to preserve local work
                force=force,  # Only force-push if user explicitly requests
            )

            if sync_result.success:
                result_msg = f"✅ Recovery successful: {sync_result.details}"
                if sync_result.commits_preserved > 0:
                    result_msg += f"\n  - Preserved {sync_result.commits_preserved} local commits"
                if sync_result.needs_manual_resolution:
                    result_msg += "\n  ⚠️ Manual push required: run with force=True to push changes"
                    warnings.append("Rebase complete but push not performed. Use force=True to push.")
            else:
                if sync_result.needs_manual_resolution:
                    result_msg = (
                        f"❌ Recovery requires manual intervention:\n"
                        f"  {sync_result.details}\n\n"
                        f"Manual recovery options:\n"
                        f"  1. Resolve conflicts and commit\n"
                        f"  2. Use operation='recover' with force=True to discard local changes\n"
                        f"  3. Manually rebase: git rebase origin/{target_branch}"
                    )
                else:
                    result_msg = f"❌ Recovery failed: {sync_result.details}"

                if sync_result.commits_lost > 0:
                    warnings.append(f"Warning: {sync_result.commits_lost} local commits may be lost")

                return ToolResult(content=[TextContent(
                    type="text",
                    text=result_msg
                )])

        else:
            return ToolResult(content=[TextContent(
                type="text",
                text=f"Error: Unknown operation '{operation}'. Must be one of: create, delete, merge, checkout, recover"
            )])

        output = {
            "success": True,
            "operation": operation,
            "branch": target_branch,
            "message": result_msg,
            "warnings": warnings,
        }

        return ToolResult(content=[TextContent(
            type="text",
            text=json.dumps(output, indent=2)
        )])

    except InvalidGitRepositoryError as e:
        return ToolResult(content=[TextContent(
            type="text",
            text=f"Error: Not a git repository: {str(e)}"
        )])
    except Exception as e:
        return ToolResult(content=[TextContent(
            type="text",
            text=f"Error syncing branch state: {str(e)}"
        )])


@mcp.tool(name="watercooler_v1_audit_branch_pairing")
def audit_branch_pairing(
    ctx: Context,
    code_path: str = "",
    include_merged: bool = False,
) -> ToolResult:
    """Comprehensive audit of branch pairing across entire repo pair.

    Scans all branches in both repos and identifies:
    - Synced branches (exist in both with same name)
    - Code-only branches (exist in code but not threads)
    - Threads-only branches (exist in threads but not code)
    - Mismatched branches

    Args:
        code_path: Path to code repository directory
        include_merged: Include fully merged branches (0 commits ahead) in report

    Returns:
        JSON report with categorized branches and recommendations.
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return ToolResult(content=[TextContent(type="text", text=error)])
        if context is None or not context.code_root or not context.threads_dir:
            return ToolResult(content=[TextContent(
                type="text",
                text="Error: Unable to resolve code and threads repo paths."
            )])

        code_repo = Repo(context.code_root, search_parent_directories=True)
        threads_repo = Repo(context.threads_dir, search_parent_directories=True)

        # Get all branches
        code_branches = {b.name for b in code_repo.heads}
        threads_branches = {b.name for b in threads_repo.heads}

        # Categorize branches
        synced = []
        code_only = []
        threads_only = []
        recommendations = []

        # Find synced branches
        for branch in code_branches & threads_branches:
            try:
                code_sha = code_repo.heads[branch].commit.hexsha[:7]
                threads_sha = threads_repo.heads[branch].commit.hexsha[:7]
                synced.append({
                    "name": branch,
                    "code_sha": code_sha,
                    "threads_sha": threads_sha,
                })
            except Exception:
                synced.append({"name": branch, "code_sha": "unknown", "threads_sha": "unknown"})

        # Find code-only branches
        for branch in code_branches - threads_branches:
            try:
                branch_obj = code_repo.heads[branch]
                commits_ahead = len(list(code_repo.iter_commits(f"main..{branch}"))) if "main" in code_branches else 0
                code_only.append({
                    "name": branch,
                    "commits_ahead": commits_ahead,
                    "action": "create_threads_branch" if commits_ahead > 0 or include_merged else "delete_if_merged",
                })
                if commits_ahead == 0 and not include_merged:
                    recommendations.append(f"Code branch '{branch}' is fully merged - consider deleting")
                else:
                    recommendations.append(f"Create threads branch '{branch}' to match code branch")
            except Exception:
                code_only.append({"name": branch, "commits_ahead": 0, "action": "unknown"})

        # Find threads-only branches
        for branch in threads_branches - code_branches:
            try:
                branch_obj = threads_repo.heads[branch]
                commits_ahead = len(list(threads_repo.iter_commits(f"main..{branch}"))) if "main" in threads_branches else 0
                threads_only.append({
                    "name": branch,
                    "commits_ahead": commits_ahead,
                    "action": "delete_or_merge" if commits_ahead == 0 or include_merged else "create_code_branch",
                })
                if commits_ahead == 0:
                    recommendations.append(f"Threads branch '{branch}' is fully merged - safe to delete")
                else:
                    recommendations.append(f"Code branch '{branch}' was deleted - merge or delete threads branch")
            except Exception:
                threads_only.append({"name": branch, "commits_ahead": 0, "action": "unknown"})

        output = {
            "synced_branches": synced,
            "code_only_branches": code_only,
            "threads_only_branches": threads_only,
            "mismatched_branches": [],  # Future: detect name mismatches
            "recommendations": recommendations,
        }

        return ToolResult(content=[TextContent(
            type="text",
            text=json.dumps(output, indent=2)
        )])

    except InvalidGitRepositoryError as e:
        return ToolResult(content=[TextContent(
            type="text",
            text=f"Error: Not a git repository: {str(e)}"
        )])
    except Exception as e:
        return ToolResult(content=[TextContent(
            type="text",
            text=f"Error auditing branch pairing: {str(e)}"
        )])


@mcp.tool(name="watercooler_v1_recover_branch_state")
def recover_branch_state(
    ctx: Context,
    code_path: str = "",
    auto_fix: bool = False,
    diagnose_only: bool = False,
) -> ToolResult:
    """Recover from branch state inconsistencies.

    Diagnoses and optionally fixes branch pairing issues:
    - Branch name mismatches
    - Orphaned threads branches (code branch deleted)
    - Missing threads branches (code branch exists)
    - Git state issues (rebase conflicts, detached HEAD, etc.)

    Args:
        code_path: Path to code repository directory
        auto_fix: Automatically apply safe fixes
        diagnose_only: Only report issues, don't fix

    Returns:
        Diagnostic report with detected issues and recommended fixes.
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return ToolResult(content=[TextContent(type="text", text=error)])
        if context is None or not context.code_root or not context.threads_dir:
            return ToolResult(content=[TextContent(
                type="text",
                text="Error: Unable to resolve code and threads repo paths."
            )])

        issues = []
        fixes_applied = []

        # Validate branch pairing
        validation_result = validate_branch_pairing(
            code_repo=context.code_root,
            threads_repo=context.threads_dir,
            strict=False,
        )

        if not validation_result.valid:
            for mismatch in validation_result.mismatches:
                issues.append({
                    "type": mismatch.type,
                    "severity": mismatch.severity,
                    "description": f"Code: {mismatch.code}, Threads: {mismatch.threads}",
                    "recovery": mismatch.recovery,
                })

                # Auto-fix if requested and safe
                if auto_fix and not diagnose_only:
                    if mismatch.type == "branch_name_mismatch" and mismatch.code:
                        try:
                            threads_repo = Repo(context.threads_dir, search_parent_directories=True)
                            if mismatch.code in [b.name for b in threads_repo.heads]:
                                threads_repo.git.checkout(mismatch.code)
                                fixes_applied.append(f"Checked out '{mismatch.code}' in threads repo")
                            else:
                                threads_repo.git.checkout('-b', mismatch.code)
                                fixes_applied.append(f"Created branch '{mismatch.code}' in threads repo")
                        except Exception as e:
                            issues.append({
                                "type": "auto_fix_failed",
                                "severity": "warning",
                                "description": f"Failed to auto-fix {mismatch.type}: {str(e)}",
                                "recovery": "Manual intervention required",
                            })

        # Check for git state issues
        try:
            code_repo = Repo(context.code_root, search_parent_directories=True)
            if code_repo.head.is_detached:
                issues.append({
                    "type": "code_repo_detached_head",
                    "severity": "warning",
                    "description": "Code repo is in detached HEAD state",
                    "recovery": "Checkout a branch: git checkout <branch>",
                })
        except Exception:
            pass

        try:
            threads_repo = Repo(context.threads_dir, search_parent_directories=True)
            if threads_repo.head.is_detached:
                issues.append({
                    "type": "threads_repo_detached_head",
                    "severity": "warning",
                    "description": "Threads repo is in detached HEAD state",
                    "recovery": "Checkout a branch: git checkout <branch>",
                })
        except Exception:
            pass

        # Check for rebase/merge conflicts
        try:
            code_repo = Repo(context.code_root, search_parent_directories=True)
            if (code_repo.git_dir / "rebase-merge").exists() or (code_repo.git_dir / "rebase-apply").exists():
                issues.append({
                    "type": "code_repo_rebase_in_progress",
                    "severity": "error",
                    "description": "Code repo has in-progress rebase",
                    "recovery": "Run: git rebase --abort (or --continue)",
                })
        except Exception:
            pass

        try:
            threads_repo = Repo(context.threads_dir, search_parent_directories=True)
            if (threads_repo.git_dir / "rebase-merge").exists() or (threads_repo.git_dir / "rebase-apply").exists():
                issues.append({
                    "type": "threads_repo_rebase_in_progress",
                    "severity": "error",
                    "description": "Threads repo has in-progress rebase",
                    "recovery": "Run: git rebase --abort (or --continue)",
                })
        except Exception:
            pass

        output = {
            "diagnosis_complete": True,
            "issues_found": len(issues),
            "issues": issues,
            "fixes_applied": fixes_applied,
            "warnings": validation_result.warnings,
        }

        return ToolResult(content=[TextContent(
            type="text",
            text=json.dumps(output, indent=2)
        )])

    except InvalidGitRepositoryError as e:
        return ToolResult(content=[TextContent(
            type="text",
            text=f"Error: Not a git repository: {str(e)}"
        )])
    except Exception as e:
        return ToolResult(content=[TextContent(
            type="text",
            text=f"Error recovering branch state: {str(e)}"
        )])


# ============================================================================
# Server Entry Point
# ============================================================================

def main():
    """Entry point for watercooler-mcp command."""
    # Get transport configuration
    transport = os.getenv("WATERCOOLER_MCP_TRANSPORT", "stdio").lower()

    if transport == "http":
        # HTTP transport configuration
        host = os.getenv("WATERCOOLER_MCP_HOST", "127.0.0.1")
        port = int(os.getenv("WATERCOOLER_MCP_PORT", "3000"))

        print(f"Starting Watercooler MCP Server on http://{host}:{port}", file=sys.stderr)
        print(f"Health check: http://{host}:{port}/health", file=sys.stderr)

        mcp.run(transport="http", host=host, port=port)
    else:
        # stdio transport (default)
        mcp.run()


if __name__ == "__main__":
    main()
