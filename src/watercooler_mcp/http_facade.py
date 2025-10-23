"""HTTP Facade for Watercooler MCP Tools

Provides a thin HTTP layer over existing watercooler functions for
Remote MCP deployment. Accepts identity headers and proxies to the
same command functions used by the FastMCP server.

Environment Variables:
- BASE_THREADS_ROOT: Root directory for per-user/per-project threads
- WATERCOOLER_GIT_REPO: Optional git sync repository
- INTERNAL_AUTH_SECRET: Shared secret for Worker -> Backend auth
"""

import os
import sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ulid import ULID

# Import existing watercooler modules
from watercooler import commands, fs
from watercooler.metadata import thread_meta
from .config import get_git_sync_manager

app = FastAPI(title="Watercooler HTTP Facade")


# ============================================================================
# Startup Validation (H5: Production Security Check)
# ============================================================================

@app.on_event("startup")
async def validate_production_config():
    """H5: Fail-fast if INTERNAL_AUTH_SECRET missing in production.

    Detects production environment and ensures critical security
    configuration is present before accepting any requests.
    """
    # Detect production environment
    is_production = (
        os.environ.get("RENDER") == "true" or  # Render deployment
        os.environ.get("ENV") == "production" or
        os.environ.get("ENVIRONMENT") == "production" or
        not os.environ.get("ALLOW_DEV_MODE")  # No explicit dev mode flag
    )

    if is_production:
        secret = os.environ.get("INTERNAL_AUTH_SECRET", "")
        if not secret:
            error_msg = (
                "FATAL: INTERNAL_AUTH_SECRET is required in production but not set.\n"
                "This is a critical security misconfiguration.\n"
                "Set INTERNAL_AUTH_SECRET environment variable or set ALLOW_DEV_MODE=true for development."
            )
            print(f"\n{'='*80}\n{error_msg}\n{'='*80}\n", file=sys.stderr)
            sys.exit(1)

        print("✅ Production config validated: INTERNAL_AUTH_SECRET is set", file=sys.stderr)
    else:
        print("⚠️  Running in development mode - INTERNAL_AUTH_SECRET not enforced", file=sys.stderr)


# ============================================================================
# Request/Response Models
# ============================================================================

class SayRequest(BaseModel):
    topic: str
    title: str
    body: str
    role: str = "implementer"
    entry_type: str = "Note"


class AckRequest(BaseModel):
    topic: str
    title: str = ""
    body: str = ""


class HandoffRequest(BaseModel):
    topic: str
    note: str = ""
    target_agent: Optional[str] = None


class SetStatusRequest(BaseModel):
    topic: str
    status: str


class ReadThreadRequest(BaseModel):
    topic: str
    from_entry: int = 0
    limit: int = 100
    format: str = "markdown"


class ListThreadsRequest(BaseModel):
    open_only: Optional[bool] = None
    limit: int = 50
    cursor: Optional[str] = None
    format: str = "markdown"


# ============================================================================
# Helper Functions
# ============================================================================

def verify_internal_auth(x_internal_auth: Optional[str]):
    """Verify internal auth header matches expected secret."""
    expected_secret = os.environ.get("INTERNAL_AUTH_SECRET", "")
    if not expected_secret:
        # If no secret configured, skip check (dev mode)
        return

    if x_internal_auth != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid internal authentication")


def derive_threads_dir(user_id: str, project_id: str) -> Path:
    """Derive per-user/per-project threads directory.

    Args:
        user_id: User identifier (e.g., 'gh:octocat')
        project_id: Project identifier (e.g., 'proj-alpha')

    Returns:
        Path to threads directory for this user/project combination
    """
    base_root = os.environ.get("BASE_THREADS_ROOT", "/tmp/watercooler")
    threads_dir = Path(base_root) / user_id / project_id
    threads_dir.mkdir(parents=True, exist_ok=True)
    return threads_dir


# ============================================================================
# Middleware for Header Extraction
# ============================================================================

@app.middleware("http")
async def extract_identity_headers(request: Request, call_next):
    """Extract and validate identity headers from Worker."""
    # Skip auth check for non-sensitive probes and metadata
    if request.method in {"HEAD", "OPTIONS"}:
        return await call_next(request)
    if request.url.path in {"/", "/health", "/openapi.json", "/docs"}:
        return await call_next(request)

    # Extract headers
    x_internal_auth = request.headers.get("X-Internal-Auth")
    x_user_id = request.headers.get("X-User-Id")
    x_agent_name = request.headers.get("X-Agent-Name")
    x_project_id = request.headers.get("X-Project-Id")

    # Verify internal auth
    verify_internal_auth(x_internal_auth)

    # Validate required headers
    if not x_user_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing X-User-Id header"}
        )

    if not x_project_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing X-Project-Id header"}
        )

    # Parse GitHub username from user_id (gh:username -> username)
    user_tag = x_user_id.split(':')[-1] if x_user_id else None

    # Set user tag in context for agents module (Remote MCP)
    from watercooler.agents import set_user_tag
    set_user_tag(user_tag)

    # Store in request state for use in endpoints
    request.state.user_id = x_user_id
    request.state.agent_name = x_agent_name or "Agent"
    request.state.user_tag = user_tag  # GitHub username for (user) tag in entries
    request.state.project_id = x_project_id

    return await call_next(request)


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "watercooler-http-facade",
        "python": sys.version.split()[0],
    }


@app.post("/mcp/watercooler_v1_health")
async def mcp_health(request: Request):
    """MCP health check."""
    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)

    return {
        "status": "healthy",
        "agent": request.state.agent_name,
        "threads_dir": str(threads_dir),
        "threads_dir_exists": threads_dir.exists(),
        "user_id": request.state.user_id,
        "project_id": request.state.project_id,
    }


@app.post("/mcp/watercooler_v1_whoami")
async def mcp_whoami(request: Request):
    """Get agent identity."""
    return {
        "agent": request.state.agent_name,
        "user_id": request.state.user_id,
        "project_id": request.state.project_id,
    }


@app.post("/mcp/watercooler_v1_list_threads")
async def mcp_list_threads(req: ListThreadsRequest, request: Request):
    """List watercooler threads."""
    if req.format != "markdown":
        raise HTTPException(
            status_code=400,
            detail="Phase 1A only supports format='markdown'"
        )

    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)
    agent = request.state.agent_name

    threads = commands.list_threads(threads_dir=threads_dir, open_only=req.open_only)

    if not threads:
        status_filter = "open " if req.open_only is True else ("closed " if req.open_only is False else "")
        return {"content": f"No {status_filter}threads found in: {threads_dir}"}

    # Format as in server.py
    agent_lower = agent.lower()
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

    output = [f"# Watercooler Threads ({len(threads)} total)\n"]

    if your_turn:
        output.append(f"\n## 🎾 Your Turn ({len(your_turn)} threads)\n")
        for title, status, ball, updated, topic, _ in your_turn:
            output.append(f"- **{topic}** - {title}")
            output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated}")

    if new_entries:
        output.append(f"\n## 🆕 NEW Entries for You ({len(new_entries)} threads)\n")
        for title, status, ball, updated, topic, has_ball in new_entries:
            marker = "🎾 " if has_ball else ""
            output.append(f"- {marker}**{topic}** - {title}")
            output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated}")

    if waiting:
        output.append(f"\n## ⏳ Waiting on Others ({len(waiting)} threads)\n")
        for title, status, ball, updated, topic, _ in waiting:
            output.append(f"- **{topic}** - {title}")
            output.append(f"  Status: {status} | Ball: {ball} | Updated: {updated}")

    output.append(f"\n---\n*You are: {agent}*")
    output.append(f"*Threads dir: {threads_dir}*")

    return {"content": "\n".join(output)}


@app.post("/mcp/watercooler_v1_read_thread")
async def mcp_read_thread(req: ReadThreadRequest, request: Request):
    """Read a watercooler thread."""
    if req.format != "markdown":
        raise HTTPException(
            status_code=400,
            detail="Phase 1A only supports format='markdown'"
        )

    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)
    sync = get_git_sync_manager()

    # Cloud mode: pull latest
    if sync:
        sync.pull()

    thread_path = fs.thread_path(req.topic, threads_dir)

    if not thread_path.exists():
        available = ', '.join(p.stem for p in threads_dir.glob('*.md')) if threads_dir.exists() else 'none'
        raise HTTPException(
            status_code=404,
            detail=f"Thread '{req.topic}' not found. Available: {available}"
        )

    content = fs.read_body(thread_path)
    return {"content": content}


@app.post("/mcp/watercooler_v1_say")
async def mcp_say(req: SayRequest, request: Request):
    """Add entry and flip ball."""
    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)
    agent = request.state.agent_name
    sync = get_git_sync_manager()

    entry_id = str(ULID())

    def append_operation():
        commands.say(
            req.topic,
            threads_dir=threads_dir,
            agent=agent,
            role=req.role,
            title=req.title,
            entry_type=req.entry_type,
            body=req.body,
            user_tag=request.state.user_tag,
        )

    if sync:
        commit_message = (
            f"{agent}: {req.title} ({req.topic})\n"
            f"\n"
            f"Watercooler-Entry-ID: {entry_id}\n"
            f"Watercooler-Topic: {req.topic}"
        )
        sync.with_sync(append_operation, commit_message)
    else:
        append_operation()

    thread_path = fs.thread_path(req.topic, threads_dir)
    _, status, ball, _ = thread_meta(thread_path)

    return {
        "content": (
            f"✅ Entry added to '{req.topic}'\n"
            f"Title: {req.title}\n"
            f"Role: {req.role} | Type: {req.entry_type}\n"
            f"Ball flipped to: {ball}\n"
            f"Status: {status}"
        )
    }


@app.post("/mcp/watercooler_v1_ack")
async def mcp_ack(req: AckRequest, request: Request):
    """Acknowledge thread without flipping ball."""
    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)
    agent = request.state.agent_name
    sync = get_git_sync_manager()

    def ack_operation():
        commands.ack(
            req.topic,
            threads_dir=threads_dir,
            agent=agent,
            title=req.title or None,
            body=req.body or None,
            user_tag=request.state.user_tag,
        )

    if sync:
        ack_title = req.title or "Ack"
        commit_message = (
            f"{agent}: {ack_title} ({req.topic})\n"
            f"\n"
            f"Watercooler-Topic: {req.topic}"
        )
        sync.with_sync(ack_operation, commit_message)
    else:
        ack_operation()

    thread_path = fs.thread_path(req.topic, threads_dir)
    _, status, ball, _ = thread_meta(thread_path)

    ack_title = req.title or "Ack"
    return {
        "content": (
            f"✅ Acknowledged '{req.topic}'\n"
            f"Title: {ack_title}\n"
            f"Ball remains with: {ball}\n"
            f"Status: {status}"
        )
    }


@app.post("/mcp/watercooler_v1_handoff")
async def mcp_handoff(req: HandoffRequest, request: Request):
    """Hand off ball to another agent."""
    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)
    agent = request.state.agent_name
    sync = get_git_sync_manager()

    if req.target_agent:
        def handoff_operation():
            commands.set_ball(req.topic, threads_dir=threads_dir, ball=req.target_agent)

            if req.note:
                commands.append_entry(
                    req.topic,
                    threads_dir=threads_dir,
                    agent=agent,
                    role="pm",
                    title=f"Handoff to {req.target_agent}",
                    entry_type="Note",
                    body=req.note,
                    ball=req.target_agent,
                    user_tag=request.state.user_tag,
                )

        if sync:
            commit_message = (
                f"{agent}: Handoff to {req.target_agent} ({req.topic})\n"
                f"\n"
                f"Watercooler-Topic: {req.topic}"
            )
            sync.with_sync(handoff_operation, commit_message)
        else:
            handoff_operation()

        return {
            "content": (
                f"✅ Ball handed off to: {req.target_agent}\n"
                f"Thread: {req.topic}\n"
                + (f"Note: {req.note}" if req.note else "")
            )
        }
    else:
        def handoff_operation():
            commands.handoff(
                req.topic,
                threads_dir=threads_dir,
                agent=agent,
                note=req.note or None,
                user_tag=request.state.user_tag,
            )

        if sync:
            commit_message = (
                f"{agent}: Handoff ({req.topic})\n"
                f"\n"
                f"Watercooler-Topic: {req.topic}"
            )
            sync.with_sync(handoff_operation, commit_message)
        else:
            handoff_operation()

        thread_path = fs.thread_path(req.topic, threads_dir)
        _, status, ball, _ = thread_meta(thread_path)

        return {
            "content": (
                f"✅ Ball handed off to: {ball}\n"
                f"Thread: {req.topic}\n"
                f"Status: {status}\n"
                + (f"Note: {req.note}" if req.note else "")
            )
        }


@app.post("/mcp/watercooler_v1_set_status")
async def mcp_set_status(req: SetStatusRequest, request: Request):
    """Update thread status."""
    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)
    agent = request.state.agent_name
    sync = get_git_sync_manager()

    def set_status_operation():
        commands.set_status(req.topic, threads_dir=threads_dir, status=req.status)

    if sync:
        commit_message = (
            f"{agent}: Status changed to {req.status} ({req.topic})\n"
            f"\n"
            f"Watercooler-Topic: {req.topic}"
        )
        sync.with_sync(set_status_operation, commit_message)
    else:
        set_status_operation()

    return {
        "content": (
            f"✅ Status updated for '{req.topic}'\n"
            f"New status: {req.status}"
        )
    }


@app.post("/mcp/watercooler_v1_reindex")
async def mcp_reindex(request: Request):
    """Generate index of all threads."""
    threads_dir = derive_threads_dir(request.state.user_id, request.state.project_id)
    agent = request.state.agent_name

    all_threads = commands.list_threads(threads_dir=threads_dir, open_only=None)

    if not all_threads:
        return {"content": f"No threads found in: {threads_dir}"}

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

    output = ["# Watercooler Index\n", f"*Generated for: {agent}*\n", f"*Total threads: {len(all_threads)}*\n"]

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
        for topic, title, status, ball, updated, is_new in closed_threads[:10]:
            output.append(f"- [{topic}]({topic}.md) - {title}")
            output.append(f"  *{status} | Updated: {updated}*")
        if len(closed_threads) > 10:
            output.append(f"\n*... and {len(closed_threads) - 10} more closed threads*")

    output.append(f"\n---\n*Threads directory: {threads_dir}*")

    return {"content": "\n".join(output)}


@app.post("/admin/sync")
async def admin_sync(request: Request):
    """Trigger a periodic git sync if configured.

    Requires X-Internal-Auth to match INTERNAL_AUTH_SECRET when set.
    No-op when git sync is not configured.
    """
    # Verify internal auth via middleware-like check
    expected = os.environ.get("INTERNAL_AUTH_SECRET")
    provided = request.headers.get("X-Internal-Auth")
    if expected and provided != expected:
        raise HTTPException(status_code=403, detail="Invalid internal authentication")

    sync = get_git_sync_manager()
    if not sync:
        return {"status": "ok", "git": "disabled"}

    # Pull latest then commit and push any local changes
    try:
        try:
            sync.pull()
        except Exception:
            # ignore pull errors here; commit may still succeed on initial clone
            pass
        pushed = sync.commit_and_push("Periodic sync")
        return {"status": "ok", "git": "enabled", "pushed": bool(pushed)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


# ============================================================================
# Development Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
