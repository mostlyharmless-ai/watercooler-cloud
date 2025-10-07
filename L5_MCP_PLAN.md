# L5: Watercooler MCP Server Implementation Plan

**Date:** 2025-10-07
**Status:** Research Phase
**Goal:** Create an MCP server for watercooler-collab using fastmcp 2.0, with cloud deployment options

## Background

During testing of watercooler-collab in a test project, we discovered a critical UX issue: when an AI agent (like Codex) starts fresh in a project with watercooler threads, they have no context about:
- What watercooler is
- How to use it
- That there are threads waiting for their response

**Solution:** Make watercooler an MCP server that exposes tools to AI agents automatically.

## Benefits of MCP Server Approach

### For Single Agent/Project
- **Auto-discovery:** AI sees watercooler tools available in environment
- **Self-documenting:** Tool descriptions explain the system
- **No manual setup:** Just works when AI starts
- **Seamless:** No need to read markdown files directly

### For Distributed Teams (Cloud Deployment)
- **Async collaboration:** Team members in different timezones
- **Unified interface:** Same tools for all AI agents (Claude, GPT, etc.)
- **Git-based sync:** Push/pull for updates
- **Concurrent access:** Advisory locking prevents conflicts

## Research Phase

### 1. fastmcp 2.0 API Research ✅ COMPLETE
Learned from Context7:
- [x] Core API for creating MCP server - `FastMCP(name="Server Name")`
- [x] Tool definition with decorators - `@mcp.tool` auto-infers name, description, schema from function signature
- [x] Tool schemas and descriptions - Uses type hints + docstrings
- [x] Authentication and user context handling - `Context` object can be injected
- [x] fastmcp cloud deployment process - HTTP transport with `mcp.run(transport="http", port=8000)`

**Key Findings:**
- Simple decorator pattern: `@mcp.tool` wraps Python functions
- Auto-schema generation from type hints (e.g., `def add(a: int, b: int) -> int`)
- Docstrings become tool descriptions for LLMs
- Both sync and async functions supported
- Resources use `@mcp.resource(uri)` decorator
- Default transport is STDIO, but HTTP available
- Can run locally or deploy to cloud

### 2. Cloudflare Deployment Research
Investigate:
- [ ] Cloudflare Workers for MCP server hosting
- [ ] Python/MCP server deployment on Cloudflare
- [ ] Compare with fastmcp cloud capabilities
- [ ] Pros/cons of each platform

### 3. Architecture Design ✅ COMPLETE

**Local MCP Server Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│ FastMCP Server (watercooler_mcp)                        │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  @mcp.tool decorated wrappers                            │
│  ├── list_threads()      → commands.list_threads()      │
│  ├── read_thread(topic)  → fs.read_body()               │
│  ├── say(...)            → commands.say()                │
│  ├── ack(...)            → commands.ack()                │
│  ├── handoff(...)        → commands.handoff()            │
│  ├── set_status(...)     → commands.set_status()         │
│  └── reindex()           → generate index                │
│                                                           │
│  Configuration:                                          │
│  ├── Auto-discover .watercooler/ in project             │
│  ├── Read WATERCOOLER_AGENT env var for identity        │
│  ├── Use local watercooler.commands API                 │
│  └── Advisory locking handled by watercooler lib        │
│                                                           │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌──────────────────────┐
              │ .watercooler/        │
              │ └── threads/         │
              │     ├── topic-1.md   │
              │     └── topic-2.md   │
              └──────────────────────┘
```

**Key Design Decisions:**

1. **Agent Identity:**
   - Read from `WATERCOOLER_AGENT` environment variable
   - Format: "AgentName" (e.g., "Codex", "Claude")
   - Falls back to "Agent" if not set
   - Configuration at MCP client level (not server)

2. **State Management:**
   - Local filesystem only for Phase 1
   - Direct access to `.watercooler/` directory
   - Uses existing watercooler-collab advisory locking
   - No git operations in local mode

3. **Tool Design:**
   - Thin wrappers around `watercooler.commands` functions
   - Preserve all watercooler-collab functionality
   - Rich docstrings for LLM understanding
   - Type hints for automatic schema generation

4. **Discovery:**
   - Auto-find `.watercooler/` in current directory
   - MCP tools are auto-discoverable by AI agents
   - No manual configuration needed

## MCP Tools to Implement

Map watercooler CLI commands → MCP tools with detailed signatures:

### 1. `list_threads()`
```python
@mcp.tool
def list_threads() -> str:
    """List all watercooler threads.

    Shows open threads where you have the ball (actionable items),
    threads where you're waiting on others, and marks NEW entries
    since you last contributed.

    Returns a formatted summary with:
    - Threads where you have the ball (🎾 marker)
    - Threads with NEW entries for you to read
    - Thread status and last update time
    """
```

### 2. `read_thread(topic: str)`
```python
@mcp.tool
def read_thread(topic: str) -> str:
    """Read the complete content of a watercooler thread.

    Args:
        topic: The thread topic identifier (e.g., "feature-auth")

    Returns the full markdown content including:
    - Thread metadata (status, ball owner, participants)
    - All entries with timestamps, authors, roles, and types
    - Current ball ownership status
    """
```

### 3. `say(topic: str, title: str, body: str, role: str = "implementer", entry_type: str = "Note")`
```python
@mcp.tool
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
        topic: Thread topic identifier
        title: Entry title (brief summary)
        body: Full entry content (markdown supported)
        role: Your role (planner/critic/implementer/tester/pm/scribe)
        entry_type: Entry type (Note/Plan/Decision/PR/Closure)

    Returns confirmation message with updated ball status.
    """
```

### 4. `ack(topic: str, title: str = "", body: str = "")`
```python
@mcp.tool
def ack(topic: str, title: str = "", body: str = "") -> str:
    """Acknowledge a thread without flipping the ball.

    Use this when you've read updates but don't need to pass the action.
    The ball stays with the current owner.

    Args:
        topic: Thread topic identifier
        title: Optional acknowledgment title
        body: Optional acknowledgment message

    Returns confirmation message.
    """
```

### 5. `handoff(topic: str, target_agent: str, note: str = "")`
```python
@mcp.tool
def handoff(topic: str, target_agent: str, note: str = "") -> str:
    """Explicitly hand off the ball to a specific agent.

    Use this to direct the conversation to a particular team member
    instead of the default counterpart.

    Args:
        topic: Thread topic identifier
        target_agent: Agent name to receive the ball
        note: Optional handoff message explaining context

    Returns confirmation with new ball owner.
    """
```

### 6. `set_status(topic: str, status: str)`
```python
@mcp.tool
def set_status(topic: str, status: str) -> str:
    """Update the status of a thread.

    Common statuses: OPEN, IN_REVIEW, CLOSED, BLOCKED

    Args:
        topic: Thread topic identifier
        status: New status value

    Returns confirmation message.
    """
```

### 7. `reindex()`
```python
@mcp.tool
def reindex() -> str:
    """Generate an index of all threads showing current status.

    Creates a summary view organized by:
    - Actionable threads (where you have the ball)
    - Open threads (waiting on others)
    - In Review threads
    - Closed threads excluded by default

    Returns the index content with links and status markers.
    """
```

## Implementation Plan

### Phase 1: Local MCP Server ⏭️ NEXT

1. **Create Package Structure**
   ```
   src/watercooler_mcp/
   ├── __init__.py
   ├── server.py       # FastMCP server instance + tool wrappers
   └── config.py       # Agent identity and directory discovery
   ```

   Add to existing `watercooler-collab` project (not separate package).

2. **Implement Core Server** (`server.py`)
   ```python
   from fastmcp import FastMCP
   from watercooler import commands
   from pathlib import Path
   import os

   mcp = FastMCP(name="Watercooler Collaboration")

   # Auto-discover configuration
   AGENT_NAME = os.getenv("WATERCOOLER_AGENT", "Agent")
   THREADS_DIR = Path.cwd() / ".watercooler"

   @mcp.tool
   def list_threads() -> str:
       # Implementation using commands.list_threads()
       pass

   @mcp.tool
   def read_thread(topic: str) -> str:
       # Implementation using fs.read_body()
       pass

   # ... other tools ...

   if __name__ == "__main__":
       mcp.run()  # Default STDIO transport
   ```

3. **Implementation Strategy**
   - Wrap existing `watercooler.commands` functions
   - Preserve all functionality (roles, types, templates)
   - Add rich docstrings for LLM guidance
   - Handle errors gracefully with helpful messages
   - Return formatted strings (not raw data structures)

4. **Test Locally**
   - Add `fastmcp` to dependencies
   - Test in `/Users/jay/projects/watercooler-test`
   - Configure Claude Desktop to use MCP server
   - Verify tool discovery and descriptions
   - Test each tool with Codex responding to test thread

### Phase 2: Cloud Deployment Features

1. **Git Integration**
   - Clone/pull before operations
   - Commit/push after modifications
   - Handle merge conflicts gracefully

2. **Multi-user Support**
   - Authentication integration
   - Agent identity detection
   - Per-user configuration

3. **Concurrent Access**
   - Advisory locking
   - Stale lock detection
   - Conflict resolution

### Phase 3: Deployment

**Option A: fastmcp cloud**
- Native MCP deployment
- Simpler setup
- Managed infrastructure

**Option B: Cloudflare Workers**
- More control
- Custom configuration
- Potentially better performance

**Decision:** Research both, choose based on capabilities

## Key Design Questions

### 1. Agent Identity
**Question:** How does MCP server know "I am Codex" vs "I am Claude"?

**Options:**
- Environment variable: `WATERCOOLER_AGENT=Codex`
- Configuration file: `.watercooler/config.json`
- Tool parameter: Agent specifies in each call
- Authentication context: From fastmcp cloud user identity

### 2. State Management (Cloud)
**Question:** Where does `.watercooler/` live?

**Options:**
- Server maintains local git clone
- Each request clones fresh (slow)
- Shared volume/storage
- Git-backed cloud storage

### 3. Git Repository
**Question:** Canonical source for threads?

**Requirements:**
- Hosted on GitHub/GitLab
- Team members have access
- Server has credentials
- Push/pull permissions

### 4. Deployment Platform
**Question:** fastmcp cloud or Cloudflare?

**Evaluation criteria:**
- Ease of deployment
- Cost
- Performance
- Control/customization
- Authentication support

## Test Project Status

**Location:** `/Users/jay/projects/watercooler-test/`

**Current state:**
- ✅ Git repository initialized
- ✅ Watercooler-collab installed (editable mode)
- ✅ `.watercooler/` directory created
- ✅ Thread created: `test-conversation`
- ✅ Initial message from Jay to Codex
- ⏸️ Waiting for MCP server to enable Codex to respond naturally

**Thread content:**
```markdown
# test-conversation — Thread
Status: OPEN
Ball: Jay (jay)
Topic: test-conversation
Created: 2025-10-07T14:56:41Z

---
Entry: Jay (jay) 2025-10-07T14:58:04Z
Type: Note
Title: Initial greeting

Hey Codex, this is a test of the watercooler-collab system.
Can you confirm you can see this and respond?
```

## Next Steps

1. ✅ ~~Fix Context7~~ (COMPLETE)
2. ✅ ~~Research fastmcp 2.0 API~~ (COMPLETE)
3. ✅ ~~Design local architecture~~ (COMPLETE)
4. ⏭️ **Build local MCP server prototype** (NEXT - Phase 1.2-1.3)
5. 🔜 **Test with Codex in watercooler-test** (Phase 1.4)
6. 📋 Research Cloudflare deployment (Phase 2 - optional)
7. 📋 Design cloud architecture (Phase 2 - optional)
8. 📋 Implement cloud features (Phase 2 - optional)
9. 📋 Deploy to chosen platform (Phase 3 - optional)

**Current Focus:** Phase 1 - Local MCP Server
**Estimated Time:** 2-3 hours for basic implementation and testing
**Success Metric:** Codex can naturally respond to watercooler threads via MCP tools

## Related Files

- `/Users/jay/projects/watercooler-collab/` - Main library
- `/Users/jay/projects/watercooler-test/` - Test project
- `/Users/jay/projects/watercooler-collab/IMPLEMENTATION_PLAN.md` - Original L1-L4 plan
- `/Users/jay/projects/watercooler-collab/docs/api.md` - Python API reference
- `/Users/jay/projects/watercooler-collab/docs/integration.md` - Integration guide

## Success Criteria

**Local MCP Server:**
- [ ] AI agent can discover watercooler tools
- [ ] AI agent can list threads where they have the ball
- [ ] AI agent can read thread content
- [ ] AI agent can respond with say/ack
- [ ] AI agent can handoff to another agent
- [ ] All tools have clear descriptions

**Cloud Deployment:**
- [ ] Multiple team members can connect
- [ ] Git sync works automatically
- [ ] Concurrent access is handled safely
- [ ] Authentication works correctly
- [ ] Performance is acceptable
- [ ] Deployment is reproducible

## Notes

- This is **L5** in the implementation plan - beyond original L1-L4 scope
- Requires coordination with fastmcp 2.0 capabilities
- Cloud deployment is optional but highly valuable for distributed teams
- Local MCP server is valuable even without cloud deployment
