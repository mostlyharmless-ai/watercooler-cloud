#!/usr/bin/env bash
# Watercooler MCP Server - Installation Helper Script
#
# This script helps register the watercooler MCP server with Claude Code.
# It provides an interactive setup process with sensible defaults.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Check if we're in the watercooler-collab directory
if [[ ! -f "pyproject.toml" ]] || ! grep -q "watercooler-collab" pyproject.toml 2>/dev/null; then
    error "This script must be run from the watercooler-collab directory"
fi

PROJECT_ROOT="$(pwd)"
SERVER_PATH="${PROJECT_ROOT}/src/watercooler_mcp/server.py"

# Check if server.py exists
if [[ ! -f "${SERVER_PATH}" ]]; then
    error "Server file not found at ${SERVER_PATH}"
fi

echo "======================================"
echo "Watercooler MCP Server Installation"
echo "======================================"
echo ""

# Step 1: Check if watercooler-collab[mcp] is installed
info "Checking installation..."
if ! python3 -c "import watercooler_mcp" 2>/dev/null; then
    echo "watercooler-collab[mcp] is not installed."
    read -p "Install now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Installing watercooler-collab[mcp]..."
        pip install -e ".[mcp]"
        success "Installation complete"
    else
        error "Installation required. Run: pip install -e .[mcp]"
    fi
else
    success "watercooler-collab[mcp] is installed"
fi

# Step 2: Get agent name
echo ""
info "What is your agent identity?"
echo "  This is how you'll appear in thread entries."
echo "  Common values: Claude, Codex, Assistant"
read -p "Agent name (default: Claude): " AGENT_NAME
AGENT_NAME=${AGENT_NAME:-Claude}

# Step 3: Get watercooler directory
echo ""
info "Where is your .watercooler directory?"
echo "  Leave blank to use dynamic discovery (./.watercooler)"
echo "  Or provide an absolute path for a specific project."
read -p "Watercooler directory (default: dynamic): " WATERCOOLER_DIR

# Step 4: Choose scope
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

# Step 5: Choose installation method
echo ""
info "Choose installation method:"
echo "  1) FastMCP install (recommended)"
echo "  2) Claude MCP add with python -m"
echo "  3) Claude MCP add with full Python path"
read -p "Method (1-3, default: 1): " METHOD_CHOICE
METHOD_CHOICE=${METHOD_CHOICE:-1}

# Build the command based on method
echo ""
info "Installing watercooler MCP server..."

case $METHOD_CHOICE in
    1)
        # FastMCP install
        CMD="fastmcp install claude-code ${SERVER_PATH} --server-name watercooler"
        CMD="${CMD} --env WATERCOOLER_AGENT=${AGENT_NAME}"
        if [[ -n "${WATERCOOLER_DIR}" ]]; then
            CMD="${CMD} --env WATERCOOLER_DIR=${WATERCOOLER_DIR}"
        fi
        ;;
    2)
        # Claude MCP add with python -m
        CMD="claude mcp add watercooler --scope ${SCOPE}"
        CMD="${CMD} -e WATERCOOLER_AGENT=${AGENT_NAME}"
        if [[ -n "${WATERCOOLER_DIR}" ]]; then
            CMD="${CMD} -e WATERCOOLER_DIR=${WATERCOOLER_DIR}"
        fi
        CMD="${CMD} -- python3 -m watercooler_mcp"
        ;;
    3)
        # Claude MCP add with full Python path
        PYTHON_PATH=$(which python3)
        CMD="claude mcp add watercooler --scope ${SCOPE}"
        CMD="${CMD} -e WATERCOOLER_AGENT=${AGENT_NAME}"
        if [[ -n "${WATERCOOLER_DIR}" ]]; then
            CMD="${CMD} -e WATERCOOLER_DIR=${WATERCOOLER_DIR}"
        fi
        CMD="${CMD} -- ${PYTHON_PATH} -m watercooler_mcp"
        ;;
esac

echo ""
echo "Command to run:"
echo "  ${CMD}"
echo ""
read -p "Proceed with installation? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    eval "${CMD}"

    echo ""
    success "Watercooler MCP server registered!"
    echo ""
    echo "Next steps:"
    echo "  1. Verify installation:"
    echo "     claude mcp list"
    echo ""
    echo "  2. In Claude Code, test with:"
    echo "     'Can you use the watercooler.v1.health tool?'"
    echo ""
    echo "Configuration:"
    echo "  Agent: ${AGENT_NAME}"
    if [[ -n "${WATERCOOLER_DIR}" ]]; then
        echo "  Directory: ${WATERCOOLER_DIR}"
    else
        echo "  Directory: ./.watercooler (dynamic)"
    fi
    echo "  Scope: ${SCOPE}"
else
    info "Installation cancelled"
    echo "You can run the command manually:"
    echo "  ${CMD}"
fi
