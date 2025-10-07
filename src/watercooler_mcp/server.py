"""Watercooler MCP Server - Phase 1A MVP

FastMCP server exposing watercooler-collab tools to AI agents.
All tools are namespaced as watercooler.v1.* for version compatibility.

Phase 1A features:
- 7 core tools + 2 diagnostic tools
- Markdown-only output (format param accepted but unused)
- Simple env-based config (WATERCOOLER_AGENT, WATERCOOLER_DIR)
- Basic error handling with helpful messages
"""

from fastmcp import FastMCP
from pathlib import Path
from watercooler import commands, fs
from .config import get_agent_name, get_threads_dir, get_version

# Initialize FastMCP server
mcp = FastMCP(name="Watercooler Collaboration")


# ============================================================================
# Diagnostic Tools (Phase 1A)
# ============================================================================

@mcp.tool(name="watercooler.v1.health")
def health() -> str:
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
        agent = get_agent_name()
        threads_dir = get_threads_dir()
        version = get_version()

        status = (
            f"Watercooler MCP Server v{version}\n"
            f"Status: Healthy\n"
            f"Agent: {agent}\n"
            f"Threads Dir: {threads_dir}\n"
            f"Threads Dir Exists: {threads_dir.exists()}\n"
        )
        return status
    except Exception as e:
        return f"Watercooler MCP Server\nStatus: Error\nError: {str(e)}"


@mcp.tool(name="watercooler.v1.whoami")
def whoami() -> str:
    """Get your resolved agent identity.

    Returns the agent name that will be used when you create entries.
    Set via WATERCOOLER_AGENT environment variable, or defaults to "Agent".

    Example:
        You are: Codex
    """
    try:
        agent = get_agent_name()
        return f"You are: {agent}"
    except Exception as e:
        return f"Error determining identity: {str(e)}"


# ============================================================================
# Core Tools (Phase 1A)
# ============================================================================

@mcp.tool(name="watercooler.v1.list_threads")
def list_threads(
    open_only: bool | None = None,
    limit: int = 50,
    cursor: str | None = None,
    format: str = "markdown"
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
        if format != "markdown":
            return f"Error: Phase 1A only supports format='markdown'. JSON support coming in Phase 1B."

        threads_dir = get_threads_dir()
        agent = get_agent_name()

        if not threads_dir.exists():
            return f"No threads directory found at: {threads_dir}\n\nCreate threads with watercooler CLI or wait for threads to be created."

        # Get thread list from commands module
        threads = commands.list_threads(threads_dir=threads_dir, open_only=open_only)

        if not threads:
            status_filter = "open " if open_only is True else ("closed " if open_only is False else "")
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

        return "\n".join(output)

    except Exception as e:
        return f"Error listing threads: {str(e)}"


@mcp.tool(name="watercooler.v1.read_thread")
def read_thread(
    topic: str,
    from_entry: int = 0,
    limit: int = 100,
    format: str = "markdown"
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

        threads_dir = get_threads_dir()
        thread_path = fs.thread_path(topic, threads_dir)

        if not thread_path.exists():
            return f"Error: Thread '{topic}' not found in {threads_dir}\n\nAvailable threads: {', '.join(p.stem for p in threads_dir.glob('*.md')) if threads_dir.exists() else 'none'}"

        # Read full thread content
        content = fs.read_body(thread_path)
        return content

    except Exception as e:
        return f"Error reading thread '{topic}': {str(e)}"


@mcp.tool(name="watercooler.v1.say")
def say(
    topic: str,
    title: str,
    body: str,
    role: str = "implementer",
    entry_type: str = "Note"
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

    Returns:
        Confirmation message with updated ball status

    Example:
        say("feature-auth", "Implementation complete", "All tests passing. Ready for review.", role="implementer", entry_type="Note")
    """
    try:
        threads_dir = get_threads_dir()
        agent = get_agent_name()

        # Call watercooler say command (auto-flips ball)
        commands.say(
            topic,
            threads_dir=threads_dir,
            agent=agent,
            role=role,
            title=title,
            entry_type=entry_type,
            body=body,
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


@mcp.tool(name="watercooler.v1.ack")
def ack(
    topic: str,
    title: str = "",
    body: str = ""
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
        threads_dir = get_threads_dir()
        agent = get_agent_name()

        # Call watercooler ack command (preserves ball)
        commands.ack(
            topic,
            threads_dir=threads_dir,
            agent=agent,
            title=title or None,  # Let command use default
            body=body or None,    # Let command use default
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


@mcp.tool(name="watercooler.v1.handoff")
def handoff(
    topic: str,
    note: str = "",
    target_agent: str | None = None
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
        threads_dir = get_threads_dir()
        agent = get_agent_name()

        if target_agent:
            # Explicit target: use set_ball to directly assign
            commands.set_ball(topic, threads_dir=threads_dir, ball=target_agent)

            # Add a note about the handoff if provided
            if note:
                commands.append_entry(
                    topic,
                    threads_dir=threads_dir,
                    agent=agent,
                    role="pm",
                    title=f"Handoff to {target_agent}",
                    entry_type="Note",
                    body=note,
                    ball=target_agent,  # Keep ball with target
                )

            return (
                f"✅ Ball handed off to: {target_agent}\n"
                f"Thread: {topic}\n"
                + (f"Note: {note}" if note else "")
            )
        else:
            # Use default handoff command (flips to counterpart)
            commands.handoff(
                topic,
                threads_dir=threads_dir,
                agent=agent,
                note=note or None,
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


@mcp.tool(name="watercooler.v1.set_status")
def set_status(
    topic: str,
    status: str
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
        threads_dir = get_threads_dir()

        # Call watercooler set_status command
        commands.set_status(topic, threads_dir=threads_dir, status=status)

        return (
            f"✅ Status updated for '{topic}'\n"
            f"New status: {status}"
        )

    except Exception as e:
        return f"Error setting status for '{topic}': {str(e)}"


@mcp.tool(name="watercooler.v1.reindex")
def reindex() -> str:
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
        agent = get_agent_name()

        if not threads_dir.exists():
            return f"No threads directory found at: {threads_dir}"

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
