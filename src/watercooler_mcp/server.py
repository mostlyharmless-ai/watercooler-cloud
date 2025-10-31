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
import os
import time
from pathlib import Path
from typing import Callable, TypeVar, Optional
from ulid import ULID
from watercooler import commands, fs
from .config import (
    ThreadContext,
    get_agent_name,
    get_threads_dir,
    get_version,
    get_git_sync_manager_from_context,
    resolve_thread_context,
)

# Initialize FastMCP server
mcp = FastMCP(name="Watercooler Cloud")


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
    if not code_path:
        return (
            "code_path required: pass the code repository root (e.g., '.') so the server can resolve the correct threads repo/branch.",
            None,
        )
    try:
        context = resolve_thread_context(Path(code_path))
    except Exception as exc:
        return (f"Error resolving code context: {exc}", None)
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
) -> T:
    sync = get_git_sync_manager_from_context(context)
    if not sync:
        return operation()

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
    return sync.with_sync(operation, commit_message)


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
) -> str:
    """List all watercooler threads.

    Shows threads where you have the ball (actionable items), threads where
    you're waiting on others, and marks NEW entries since you last contributed.

    Args:
        open_only: Filter by open status (True=open only, False=closed only, None=all)
        limit: Maximum threads to return (Phase 1A: ignored, returns all)
        cursor: Pagination cursor (Phase 1A: ignored, no pagination)
        format: Output format - "markdown" or "json" (Phase 1A: only "markdown" supported)

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
            return f"Error: Phase 1A only supports format='markdown'. JSON support coming in Phase 1B."

        error, context = _require_context(code_path)
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."
        _log_context(context, f"list_threads start code_path={code_path!r} open_only={open_only}")
        if context and _dynamic_context_missing(context):
            _log_context(context, "list_threads dynamic context missing")
            return (
                "Dynamic threads repo was not resolved from your git context.\n"
                "Run from inside your code repo or set WATERCOOLER_CODE_REPO/WATERCOOLER_GIT_REPO on the MCP server.\n"
                f"Resolved threads dir: {context.threads_dir} (local fallback).\n"
                f"Code root: {context.code_root or Path.cwd()}"
            )

        agent = get_agent_name(ctx.client_id)
        _log_context(context, "list_threads refreshing git state")
        _refresh_threads(context)
        threads_dir = context.threads_dir

        # Create threads directory if it doesn't exist
        if not threads_dir.exists():
            threads_dir.mkdir(parents=True, exist_ok=True)
            _log_context(context, "list_threads created empty threads directory")
            return f"No threads found. Threads directory created at: {threads_dir}\n\nCreate your first thread with watercooler_v1_say."

        # Get thread list from commands module
        scan_start = time.time()
        threads = commands.list_threads(threads_dir=threads_dir, open_only=open_only)
        scan_elapsed = time.time() - scan_start
        _log_context(context, f"list_threads scanned {len(threads)} threads in {scan_elapsed:.2f}s")

        if not threads:
            status_filter = "open " if open_only is True else ("closed " if open_only is False else "")
            _log_context(context, f"list_threads no {status_filter or ''}threads found")
            return f"No {status_filter}threads found in: {threads_dir}"

        # Format output
        agent_lower = agent.lower()
        output = []
        output.append(f"# Watercooler Threads ({len(threads)} total)\n")

        # Separate threads by ball ownership
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

        # Your turn section
        if your_turn:
            output.append(f"\n## 🎾 Your Turn ({len(your_turn)} threads)\n")
            for title, status, ball, updated, topic, _ in your_turn:
                output.append(f"- **{topic}** - {title}")
                output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated}")

        # NEW entries section
        if new_entries:
            output.append(f"\n## 🆕 NEW Entries for You ({len(new_entries)} threads)\n")
            for title, status, ball, updated, topic, has_ball in new_entries:
                marker = "🎾 " if has_ball else ""
                output.append(f"- {marker}**{topic}** - {title}")
                output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated}")

        # Waiting section
        if waiting:
            output.append(f"\n## ⏳ Waiting on Others ({len(waiting)} threads)\n")
            for title, status, ball, updated, topic, _ in waiting:
                output.append(f"- **{topic}** - {title}")
                output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated}")

        output.append(f"\n---\n*You are: {agent}*")
        output.append(f"*Threads dir: {threads_dir}*")

        response = "\n".join(output)
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

        return response

    except Exception as e:
        _log_context(None, f"list_threads error: {e}")
        return f"Error listing threads: {str(e)}"


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
        body: Full entry content (markdown supported)
        role: Your role - planner, critic, implementer, tester, pm, or scribe (default: implementer)
        entry_type: Entry type - Note, Plan, Decision, PR, or Closure (default: Note)
        create_if_missing: Whether to create the thread if it doesn't exist (default: False, but threads are auto-created by commands.say)

    Returns:
        Confirmation message with updated ball status

    Example:
        say("feature-auth", "Implementation complete", "All tests passing. Ready for review.", role="implementer", entry_type="Note")
    """
    try:
        error, context = _require_context(code_path)
        if error:
            return error
        if context is None:
            return "Error: Unable to resolve code context for the provided code_path."

        if not agent_func or ":" not in agent_func:
            return "identity required: pass agent_func as '<AgentBase>:<spec>' (e.g., 'Claude:pm')"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<AgentBase>:<spec>'"

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

    Returns:
        Confirmation message

    Example:
        ack("feature-auth", "Noted", "Thanks for the update, looks good!")
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
            return "identity required: pass agent_func as '<AgentBase>:<spec>'"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<AgentBase>:<spec>'"
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

    Returns:
        Confirmation with new ball owner

    Example:
        handoff("feature-auth", "Ready for your review", target_agent="Claude")
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
            return "identity required: pass agent_func as '<AgentBase>:<spec>'"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<AgentBase>:<spec>'"
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

    Returns:
        Confirmation message

    Example:
        set_status("feature-auth", "IN_REVIEW")
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
            return "identity required: pass agent_func as '<AgentBase>:<spec>'"
        agent_base, agent_spec = [p.strip() for p in agent_func.split(":", 1)]
        if not agent_base or not agent_spec:
            return "identity invalid: agent_func must be '<AgentBase>:<spec>'"
        threads_dir = context.threads_dir

        def op():
            commands.set_status(topic, threads_dir=threads_dir, status=status)

        run_with_sync(
            context,
            f"{agent_base}: Status changed to {status} ({topic})",
            op,
            topic=topic,
            agent_spec=agent_spec,
        )

        return (
            f"✅ Status updated for '{topic}'\n"
            f"New status: {status}"
        )

    except Exception as e:
        return f"Error setting status for '{topic}': {str(e)}"


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
# Server Entry Point
# ============================================================================

def main():
    """Entry point for watercooler-mcp command."""
    mcp.run()


if __name__ == "__main__":
    main()
