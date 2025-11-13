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
from fastmcp import FastMCP, Context
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
import os
import time
import json
from pathlib import Path
from typing import Callable, TypeVar, Optional, Dict, List
from ulid import ULID
from git import Repo, InvalidGitRepositoryError, GitCommandError
from watercooler import commands, fs
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
    validate_branch_pairing,
    GitSyncManager,
    _diag,
)

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

# Initialize FastMCP server
mcp = FastMCP(name="Watercooler Cloud")


# Instrument FastMCP tool execution to debug hanging responses
try:
    from fastmcp.tools.tool import FunctionTool  # type: ignore

    _orig_run = FunctionTool.run

    async def _instrumented_run(self, arguments):  # type: ignore
        result = await _orig_run(self, arguments)
        try:
            _log_context(None, f"FunctionTool.run completed for {getattr(self, 'name', '<unknown>')}")
            # Workaround: Force stdout flush on Windows after tool execution
            # This may help clear stdio blockage before FastMCP writes response
            if sys.platform == "win32":
                sys.stdout.flush()
                sys.stderr.flush()
        except Exception:
            pass
        return result

    FunctionTool.run = _instrumented_run  # type: ignore
except Exception:
    pass


T = TypeVar("T")


_MCP_LOG_ENABLED = os.getenv("WATERCOOLER_MCP_LOG", "0").lower() not in {"0", "false", "off"}


def _log_context(ctx: Optional[ThreadContext], message: str) -> None:
    if not _MCP_LOG_ENABLED:
        return
    try:
        base = Path(ctx.threads_dir) if ctx else Path.cwd()
        log_path = base.parent / ".watercooler-mcp.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{timestamp} {message}\n")
    except Exception:
        pass


def _should_auto_branch() -> bool:
    return os.getenv("WATERCOOLER_AUTO_BRANCH", "1") != "0"


def _require_context(code_path: str) -> tuple[str | None, ThreadContext | None]:
    _diag(f"_require_context: entry with code_path={code_path!r}")
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
        _diag(f"_require_context: calling resolve_thread_context({code_path!r})")
        context = resolve_thread_context(Path(code_path))
        _diag(f"_require_context: resolve_thread_context returned")
    except Exception as exc:
        _diag(f"_require_context: exception from resolve_thread_context: {exc}")
        return (f"Error resolving code context: {exc}", None)
    _diag(f"_require_context: exit, returning context")
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


def _refresh_threads(context: ThreadContext) -> None:
    sync = get_git_sync_manager_from_context(context)
    if not sync:
        return
    branch = context.code_branch
    if branch and _should_auto_branch():
        try:
            sync.ensure_branch(branch)
        except Exception:
            pass
    status = sync.get_async_status()
    if status.get("mode") == "async":
        # Async mode relies on background pulls; avoid blocking operations.
        return
    sync.pull()


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

    # Validate branch pairing before write operation
    if not skip_validation and context.code_root and context.threads_dir:
        try:
            validation_result = validate_branch_pairing(
                code_repo=context.code_root,
                threads_repo=context.threads_dir,
                strict=True,
            )
            if not validation_result.valid:
                # Build error message with recovery steps
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
                    "\nTo fix: Use watercooler_v1_sync_branch_state to sync branches, "
                    "or set skip_validation=True to bypass (not recommended)."
                )
                raise BranchPairingError("\n".join(error_parts))
        except BranchPairingError:
            raise
        except Exception as e:
            # Log but don't block on validation errors (e.g., repo not initialized)
            _diag(f"Branch validation warning: {e}")

    branch = context.code_branch
    if branch and _should_auto_branch():
        try:
            sync.ensure_branch(branch)
        except Exception:
            pass

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
        _log_context(context, f"list_threads start code_path={code_path!r} open_only={open_only}")
        if context and _dynamic_context_missing(context):
            _log_context(context, "list_threads dynamic context missing")
            return ToolResult(content=[TextContent(type="text", text=(
                "Dynamic threads repo was not resolved from your git context.\n"
                "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO on the MCP server.\n"
                f"Resolved threads dir: {context.threads_dir} (local fallback).\n"
                f"Code root: {context.code_root or Path.cwd()}"
            ))])

        agent = get_agent_name(ctx.client_id)
        _log_context(context, "list_threads refreshing git state")
        git_start = time.time()
        _refresh_threads(context)
        git_elapsed = time.time() - git_start
        _log_context(context, f"list_threads git refreshed in {git_elapsed:.2f}s")
        threads_dir = context.threads_dir

        # Create threads directory if it doesn't exist
        if not threads_dir.exists():
            threads_dir.mkdir(parents=True, exist_ok=True)
            _log_context(context, "list_threads created empty threads directory")
            return ToolResult(content=[TextContent(type="text", text=f"No threads found. Threads directory created at: {threads_dir}\n\nCreate your first thread with watercooler_v1_say.")])

        # Get thread list from commands module
        scan_start = time.time()
        threads = commands.list_threads(threads_dir=threads_dir, open_only=open_only)
        scan_elapsed = time.time() - scan_start
        _log_context(context, f"list_threads scanned {len(threads)} threads in {scan_elapsed:.2f}s")

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
            _log_context(context, f"list_threads no {status_filter or ''}threads found")
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
        _log_context(context, f"list_threads classified threads in {classify_elapsed:.2f}s (your_turn={len(your_turn)} waiting={len(waiting)} new={len(new_entries)})")

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
        _log_context(context, f"list_threads rendered markdown sections in {render_elapsed:.2f}s")
        duration = time.time() - start_ts
        _log_context(
            context,
            (
                "list_threads formatted response in "
                f"{duration:.2f}s (total={len(threads)} new={len(new_entries)} "
                f"your_turn={len(your_turn)} waiting={len(waiting)} "
                f"chars={len(response)})"
            ),
        )
        _log_context(context, "list_threads returning response")
        return ToolResult(content=[TextContent(type="text", text=response)])

    except Exception as e:
        _log_context(None, f"list_threads error: {e}")
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
        if format != "markdown":
            return f"Error: Phase 1A only supports format='markdown'. JSON support coming in Phase 1B."

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
        return content

    except Exception as e:
        return f"Error reading thread '{topic}': {str(e)}"


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
    _diag(f"TOOL_ENTRY: watercooler_v1_sync(code_path={code_path!r}, action={action!r})")
    try:
        _diag("TOOL_STEP: calling _require_context")
        error, context = _require_context(code_path)
        _diag(f"TOOL_STEP: _require_context returned (error={error!r}, context={'present' if context else 'None'})")
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."

        _diag("TOOL_STEP: calling get_git_sync_manager_from_context")
        sync = get_git_sync_manager_from_context(context)
        _diag(f"TOOL_STEP: get_git_sync_manager returned {'present' if sync else 'None'}")
        if not sync:
            return "Async sync unavailable: no git-enabled threads repository for this context."

        action_normalized = (action or "now").strip().lower()
        _diag(f"TOOL_STEP: action_normalized={action_normalized!r}")

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
            _diag("TOOL_STEP: calling sync.get_async_status()")
            status = sync.get_async_status()
            _diag(f"TOOL_STEP: get_async_status returned {len(status)} keys")
            result = _format_status(status)
            _diag(f"TOOL_STEP: formatted status, length={len(result)}")
            _diag("TOOL_EXIT: returning status result")
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

    Note:
        This operational tool does **not** require ``agent_func`` or other
        provenance parameters. Unlike write operations (``watercooler_v1_say``,
        ``watercooler_v1_ack``, etc.), it only performs git lifecycle
        management, so pass just ``code_path``, ``branch``, ``operation``, and
        ``force``. FastMCP will automatically reject any unexpected parameters.

    Args:
        code_path: Path to code repository directory (default: current directory)
        branch: Specific branch to sync (default: current branch)
        operation: One of "create", "delete", "merge", "checkout" (default: "checkout")
        force: Skip safety checks (use with caution, default: False)

    Returns:
        Operation result with success/failure and any warnings.

    Example:
        >>> sync_branch_state(ctx, code_path=".", branch="feature-auth", operation="checkout")
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
                result_msg = f"✅ Merged '{target_branch}' into 'main' in threads repo."
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

        else:
            return ToolResult(content=[TextContent(
                type="text",
                text=f"Error: Unknown operation '{operation}'. Must be one of: create, delete, merge, checkout"
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
    mcp.run()


if __name__ == "__main__":
    main()
