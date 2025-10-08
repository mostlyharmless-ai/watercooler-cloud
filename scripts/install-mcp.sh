#!/usr/bin/env bash
# Watercooler MCP Server - Installation Helper Script
#
# Registers the Watercooler MCP server with clients and sets up shared
# configuration so Claude and Codex can collaborate on the same threads.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
error() { echo -e "${RED}Error: $1${NC}" >&2; exit 1; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

# Ensure we are in repo root
if [[ ! -f "pyproject.toml" ]] || ! grep -q "watercooler-collab" pyproject.toml 2>/dev/null; then
  error "This script must be run from the watercooler-collab directory"
fi

PROJECT_ROOT="$(pwd)"
SERVER_PATH="${PROJECT_ROOT}/src/watercooler_mcp/server.py"
[[ -f "${SERVER_PATH}" ]] || error "Server file not found at ${SERVER_PATH}"

echo "======================================"
echo "Watercooler MCP Server Installation"
echo "======================================"
echo ""

# Step 0: Choose target client(s)
info "Choose target client:"
echo "  1) Claude (Claude Code/Desktop)"
echo "  2) Codex (CLI / VS Code via Cline)"
echo "  3) Both (Claude + Codex)"
read -p "Client (1-3, default: 1): " CLIENT_CHOICE
CLIENT_CHOICE=${CLIENT_CHOICE:-1}
case $CLIENT_CHOICE in
  1) CLIENT="claude" ; DEFAULT_AGENT="Claude" ;;
  2) CLIENT="codex"  ; DEFAULT_AGENT="Codex"  ;;
  3) CLIENT="both"   ; DEFAULT_AGENT="Claude" ;;
  *) error "Invalid client choice" ;;
esac

# Step 1: Ensure package (with MCP extras) is available
info "Checking installation..."

# Always use python3 as the interpreter
PY="$(command -v python3 || true)"
[[ -n "${PY}" ]] || error "python3 not found. Please install Python 3.9+ and ensure it is on PATH."

if ! "${PY}" -c "import watercooler_mcp" 2>/dev/null; then
  echo "watercooler-collab[mcp] is not installed."
  read -p "Install now? (y/n) " -n 1 -r; echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    info "Installing watercooler-collab[mcp]..."
    "${PY}" -m pip install -e ".[mcp]"
    success "Installation complete"
  else
    error "Installation required. Run: pip install -e .[mcp]"
  fi
else
  success "watercooler-collab[mcp] is installed"
fi

# Step 2: Agent identity overrides (optional)
echo ""
info "Agent identity (optional):"
echo "  Defaults: Claude → 'Claude', Codex → 'Codex' (or client-provided)."
if [[ "${CLIENT}" == "both" ]]; then
  read -p "Claude agent override (default: Claude, blank=auto): " AGENT_NAME_CLAUDE
  read -p "Codex agent override  (default: Codex,  blank=auto): " AGENT_NAME_CODEX
else
  read -p "Agent name override (default: ${DEFAULT_AGENT}, blank=auto): " AGENT_NAME
  if [[ -z "${AGENT_NAME}" && "${CLIENT}" == "codex" ]]; then
    AGENT_NAME="${DEFAULT_AGENT}"
  fi
fi

# Step 3: Threads directory
echo ""
info "Where is your .watercooler directory?"
echo "  Leave blank to use dynamic discovery (./.watercooler)"
echo "  Or provide an absolute path for a specific project."
read -p "Watercooler directory (default: dynamic): " WATERCOOLER_DIR

# Step 3b: Codex/Shared agent registry (optional)
if [[ "${CLIENT}" == "codex" || "${CLIENT}" == "both" ]]; then
  echo ""
  info "Configure agent registry (agents.json) for counterpart mappings?"
  echo "  Adds canonical names and counterpart flow (Codex ↔ Claude)."
  read -p "Create/update agents.json in threads dir? (y/n, default: y): " REGISTRY_CHOICE
  REGISTRY_CHOICE=${REGISTRY_CHOICE:-y}
  if [[ ${REGISTRY_CHOICE} =~ ^[Yy]$ ]]; then
    THREADS_DIR=${WATERCOOLER_DIR:-"${PROJECT_ROOT}/.watercooler"}
    mkdir -p "${THREADS_DIR}"
    AGENTS_FILE="${THREADS_DIR}/agents.json"
    info "Writing ${AGENTS_FILE}"
    cat > "${AGENTS_FILE}" <<'JSON'
{
  "canonical": {
    "claude": "Claude",
    "codex": "Codex",
    "team": "Team"
  },
  "counterpart": {
    "Codex": "Claude",
    "Claude": "Codex",
    "Team": "Claude"
  },
  "default_ball": "Team"
}
JSON
    success "Agent registry configured for Codex ↔ Claude"
  fi
fi

# Step 4: Scope for Claude registration
echo ""
info "Choose configuration scope:"
echo "  1) local  - Current directory only"
echo "  2) user   - All projects (recommended for dynamic directory)"
echo "  3) project - Specific project"
read -p "Scope (1-3, default: 2): " SCOPE_CHOICE
SCOPE_CHOICE=${SCOPE_CHOICE:-2}
case $SCOPE_CHOICE in
  1) SCOPE="local" ;;
  2) SCOPE="user" ;;
  3) SCOPE="project" ;;
  *) error "Invalid scope choice" ;;
esac

# Step 5: Choose installation methods
echo ""
info "Choose installation method:"
if [[ "${CLIENT}" == "claude" ]]; then
  echo "  1) Claude MCP add with python -m (recommended)"
  echo "  2) Claude MCP add with full Python path"
  echo "  3) FastMCP install for Claude Code"
  read -p "Method (1-3, default: 1): " METHOD_CHOICE
  METHOD_CHOICE=${METHOD_CHOICE:-1}
elif [[ "${CLIENT}" == "codex" ]]; then
  echo "  4) Update ~/.codex/config.toml (Codex CLI)"
  read -p "Method (4, default: 4): " METHOD_CHOICE
  METHOD_CHOICE=${METHOD_CHOICE:-4}
else
  echo "  Claude methods:"
  echo "    1) Claude MCP add with python -m (recommended)"
  echo "    2) Claude MCP add with full Python path"
  echo "    3) FastMCP install for Claude Code"
  read -p "Claude method (1-3, default: 1): " METHOD_CHOICE_CLAUDE
  METHOD_CHOICE_CLAUDE=${METHOD_CHOICE_CLAUDE:-1}
  echo "  Codex methods:"
  echo "    4) Update ~/.codex/config.toml (Codex CLI)"
  read -p "Codex method (4, default: 4): " METHOD_CHOICE_CODEX
  METHOD_CHOICE_CODEX=${METHOD_CHOICE_CODEX:-4}
fi

# Step 6: Build command(s)
echo ""; info "Installing watercooler MCP server..."

if [[ "${CLIENT}" == "claude" ]]; then
  case $METHOD_CHOICE in
    1)
      if ! command -v claude >/dev/null 2>&1; then
        error "'claude' CLI not found in PATH. Install Claude Desktop and ensure the 'claude' CLI is available, or use the VS Code/Cline snippet option. See docs/CLAUDE_DESKTOP_SETUP.md."
      fi
      CMD="claude mcp add watercooler --scope ${SCOPE}"
      [[ -n "${AGENT_NAME}" ]] && CMD+=" -e WATERCOOLER_AGENT=${AGENT_NAME}"
      [[ -n "${WATERCOOLER_DIR}" ]] && CMD+=" -e WATERCOOLER_DIR=${WATERCOOLER_DIR}"
      CMD+=" -- ${PY} -m watercooler_mcp"
      ;;
    2)
      if ! command -v claude >/dev/null 2>&1; then
        error "'claude' CLI not found in PATH. Install Claude Desktop and ensure the 'claude' CLI is available, or use the VS Code/Cline snippet option. See docs/CLAUDE_DESKTOP_SETUP.md."
      fi
      PYTHON_PATH="${PY}"
      CMD="claude mcp add watercooler --scope ${SCOPE}"
      [[ -n "${AGENT_NAME}" ]] && CMD+=" -e WATERCOOLER_AGENT=${AGENT_NAME}"
      [[ -n "${WATERCOOLER_DIR}" ]] && CMD+=" -e WATERCOOLER_DIR=${WATERCOOLER_DIR}"
      CMD+=" -- ${PYTHON_PATH} -m watercooler_mcp"
      ;;
    3)
      if ! command -v fastmcp >/dev/null 2>&1; then
        error "'fastmcp' CLI not found. It is provided by the fastmcp package. Try: ${PY} -m pip install fastmcp, or use a different method."
      fi
      CMD="fastmcp install claude-code ${SERVER_PATH}"
      [[ -n "${AGENT_NAME}" ]] && CMD+=" --env WATERCOOLER_AGENT=${AGENT_NAME}"
      [[ -n "${WATERCOOLER_DIR}" ]] && CMD+=" --env WATERCOOLER_DIR=${WATERCOOLER_DIR}"
      ;;
    *) error "Invalid method for Claude" ;;
  esac
elif [[ "${CLIENT}" == "codex" ]]; then
  case $METHOD_CHOICE in
    4) CODEX_TOML=1 ;;
    *) error "Invalid method for Codex" ;;
  esac
else
  # both
  case $METHOD_CHOICE_CLAUDE in
    1)
      CMD_CLAUDE="claude mcp add watercooler --scope ${SCOPE}"
      [[ -n "${AGENT_NAME_CLAUDE}" ]] && CMD_CLAUDE+=" -e WATERCOOLER_AGENT=${AGENT_NAME_CLAUDE}" || CMD_CLAUDE+=" -e WATERCOOLER_AGENT=Claude"
      [[ -n "${WATERCOOLER_DIR}" ]] && CMD_CLAUDE+=" -e WATERCOOLER_DIR=${WATERCOOLER_DIR}"
      CMD_CLAUDE+=" -- python3 -m watercooler_mcp"
      ;;
    2)
      PYTHON_PATH="python3"
      CMD_CLAUDE="claude mcp add watercooler --scope ${SCOPE}"
      [[ -n "${AGENT_NAME_CLAUDE}" ]] && CMD_CLAUDE+=" -e WATERCOOLER_AGENT=${AGENT_NAME_CLAUDE}" || CMD_CLAUDE+=" -e WATERCOOLER_AGENT=Claude"
      [[ -n "${WATERCOOLER_DIR}" ]] && CMD_CLAUDE+=" -e WATERCOOLER_DIR=${WATERCOOLER_DIR}"
      CMD_CLAUDE+=" -- ${PYTHON_PATH} -m watercooler_mcp"
      ;;
    3)
      CMD_CLAUDE="fastmcp install claude-code ${SERVER_PATH}"
      [[ -n "${AGENT_NAME_CLAUDE}" ]] && CMD_CLAUDE+=" --env WATERCOOLER_AGENT=${AGENT_NAME_CLAUDE}" || CMD_CLAUDE+=" --env WATERCOOLER_AGENT=Claude"
      [[ -n "${WATERCOOLER_DIR}" ]] && CMD_CLAUDE+=" --env WATERCOOLER_DIR=${WATERCOOLER_DIR}"
      ;;
    *) error "Invalid method for Claude" ;;
  esac
  # Codex method
  case $METHOD_CHOICE_CODEX in
    4) CODEX_TOML=1 ;;
    *) error "Invalid method for Codex" ;;
  esac
fi

# Step 7: Show commands/snippets
echo ""; echo "Command / Snippet:"
if [[ "${CLIENT}" == "both" ]]; then
  echo ""; echo "[Claude]"; echo "  ${CMD_CLAUDE}"
  echo ""; echo "[Codex] - Will update ~/.codex/config.toml with:"
  cat <<TOML
  [mcp_servers.watercooler]
  command = "python3"
  args = ["-m", "watercooler_mcp"]

  [mcp_servers.watercooler.env]
  WATERCOOLER_AGENT = "${AGENT_NAME_CODEX:-Codex}"
TOML
  if [[ -n "${WATERCOOLER_DIR}" ]]; then
    echo "  WATERCOOLER_DIR = \"${WATERCOOLER_DIR}\""
  fi
else
  if [[ "${CLIENT}" == "codex" && -n "${CODEX_TOML}" ]]; then
    echo "  Will update ~/.codex/config.toml with:"
    cat <<TOML
  [mcp_servers.watercooler]
  command = "python3"
  args = ["-m", "watercooler_mcp"]

  [mcp_servers.watercooler.env]
  WATERCOOLER_AGENT = "${AGENT_NAME:-Codex}"
TOML
    if [[ -n "${WATERCOOLER_DIR}" ]]; then
      echo "  WATERCOOLER_DIR = \"${WATERCOOLER_DIR}\""
    fi
  else
    echo "  ${CMD}"
  fi
fi

echo ""; read -p "Proceed with installation? (y/n) " -n 1 -r; echo

# Step 8: Execute registration (Claude) and finish
if [[ $REPLY =~ ^[Yy]$ ]]; then
  if [[ "${CLIENT}" == "claude" ]]; then
    set +e
    eval "${CMD}"
    RC=$?
    set -e
    if [[ ${RC} -ne 0 ]]; then
      error "Claude registration command failed (exit ${RC}). Review the command above and see docs/CLAUDE_DESKTOP_SETUP.md."
    fi
    echo ""; success "Watercooler MCP server registered!"
    echo ""; echo "Next steps:"; echo "  1. Verify installation:"; echo "     claude mcp list"; echo ""
    echo "  2. In Claude Code, test with:"; echo "     'Can you use the watercooler_v1_health tool?'"
  elif [[ "${CLIENT}" == "codex" ]]; then
    # Write to ~/.codex/config.toml
    CODEX_CONFIG="${HOME}/.codex/config.toml"
    mkdir -p "${HOME}/.codex"

    # Check if config exists and has watercooler section
    if [[ -f "${CODEX_CONFIG}" ]] && grep -q "\[mcp_servers.watercooler\]" "${CODEX_CONFIG}"; then
      info "Updating existing watercooler configuration in ${CODEX_CONFIG}"
      # Remove existing watercooler section
      sed -i.bak '/\[mcp_servers\.watercooler\]/,/^$/d' "${CODEX_CONFIG}"
    else
      info "Adding watercooler configuration to ${CODEX_CONFIG}"
    fi

    # Append new configuration
    cat >> "${CODEX_CONFIG}" <<TOML

# Watercooler MCP server
[mcp_servers.watercooler]
command = "python3"
args = ["-m", "watercooler_mcp"]

[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "${AGENT_NAME:-Codex}"
TOML

    if [[ -n "${WATERCOOLER_DIR}" ]]; then
      echo "WATERCOOLER_DIR = \"${WATERCOOLER_DIR}\"" >> "${CODEX_CONFIG}"
    fi

    success "Updated ${CODEX_CONFIG}"
    echo ""; echo "Next steps:"
    echo "  1. Restart Codex to load the new configuration"
    echo "  2. Test with: watercooler_v1_health"
  else
    # Both Claude and Codex
    eval "${CMD_CLAUDE}"; echo ""; success "Claude MCP registration completed."

    # Write Codex config
    CODEX_CONFIG="${HOME}/.codex/config.toml"
    mkdir -p "${HOME}/.codex"

    if [[ -f "${CODEX_CONFIG}" ]] && grep -q "\[mcp_servers.watercooler\]" "${CODEX_CONFIG}"; then
      info "Updating existing watercooler configuration in ${CODEX_CONFIG}"
      sed -i.bak '/\[mcp_servers\.watercooler\]/,/^$/d' "${CODEX_CONFIG}"
    else
      info "Adding watercooler configuration to ${CODEX_CONFIG}"
    fi

    cat >> "${CODEX_CONFIG}" <<TOML

# Watercooler MCP server
[mcp_servers.watercooler]
command = "python3"
args = ["-m", "watercooler_mcp"]

[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "${AGENT_NAME_CODEX:-Codex}"
TOML

    if [[ -n "${WATERCOOLER_DIR}" ]]; then
      echo "WATERCOOLER_DIR = \"${WATERCOOLER_DIR}\"" >> "${CODEX_CONFIG}"
    fi

    success "Updated ${CODEX_CONFIG}"
  fi

  echo ""; echo "Configuration:"
  if [[ "${CLIENT}" == "both" ]]; then
    echo "  Claude Agent: ${AGENT_NAME_CLAUDE:-auto (Claude)}"
    echo "  Codex Agent:  ${AGENT_NAME_CODEX:-auto (Codex)}"
  else
    if [[ -n "${AGENT_NAME}" ]]; then
      echo "  Agent: ${AGENT_NAME}"
    else
      echo "  Agent: Auto-detected from MCP client"
    fi
  fi
  if [[ -n "${WATERCOOLER_DIR}" ]]; then
    echo "  Directory: ${WATERCOOLER_DIR}"
  else
    echo "  Directory: ./.watercooler (dynamic)"
  fi
  echo "  Scope: ${SCOPE}"
else
  info "Installation cancelled"
  if [[ "${CLIENT}" == "claude" ]]; then
    echo "You can run this manually:"
    echo "${CMD}"
  elif [[ "${CLIENT}" == "codex" ]]; then
    echo "You can manually add to ~/.codex/config.toml:"
    cat <<TOML

[mcp_servers.watercooler]
command = "python3"
args = ["-m", "watercooler_mcp"]

[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "${AGENT_NAME:-Codex}"
TOML
    if [[ -n "${WATERCOOLER_DIR}" ]]; then
      echo "WATERCOOLER_DIR = \"${WATERCOOLER_DIR}\""
    fi
  else
    echo "[Claude] ${CMD_CLAUDE}"
    echo "[Codex] Manually add to ~/.codex/config.toml (see preview above)"
  fi
fi
