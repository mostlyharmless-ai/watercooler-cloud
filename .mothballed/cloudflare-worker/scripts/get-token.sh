#!/usr/bin/env bash
set -euo pipefail

# Watercooler Cloud - Get Bearer Token for MCP
#
# This script helps you obtain a Bearer token for authenticating with
# watercooler-cloud MCP servers and automatically configures Claude CLI.
#
# Usage:
#   ./scripts/get-token.sh <staging|production> <user|project>
#
# Arguments:
#   staging|production - Which environment to configure
#   user|project      - Scope for MCP configuration
#                       user: ~/.claude.json (all projects)
#                       project: ./.claude.json (this project only)
#
# Output:
#   Automatically configures Claude CLI with MCP server

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Change to worker directory
cd "$(dirname "$0")/.." || exit 1

# Parse arguments
ENV="${1:-}"
SCOPE="${2:-}"

if [[ "$ENV" != "staging" && "$ENV" != "production" ]]; then
  echo -e "${RED}Usage: $0 <staging|production> <user|project>${NC}"
  echo ""
  echo "Arguments:"
  echo "  staging|production  - Which environment to configure"
  echo "  user|project        - Configuration scope"
  echo "                        user: ~/.claude.json (all projects)"
  echo "                        project: ./.claude.json (this project only)"
  exit 1
fi

if [[ "$SCOPE" != "user" && "$SCOPE" != "project" ]]; then
  echo -e "${RED}Usage: $0 <staging|production> <user|project>${NC}"
  echo ""
  echo -e "${YELLOW}Second argument must be 'user' or 'project'${NC}"
  exit 1
fi

# Set URLs and names based on environment
if [[ "$ENV" == "staging" ]]; then
  WORKER_URL="https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev"
  MCP_NAME="watercooler-cloud-staging"
  ENV_NAME="Staging"
else
  WORKER_URL="https://watercooler-cloud.mostlyharmless-ai.workers.dev"
  MCP_NAME="watercooler-cloud"
  ENV_NAME="Production"
fi

SSE_URL="${WORKER_URL}/sse?project=watercooler-cloud"

echo -e "${BLUE}=== Watercooler Cloud MCP Setup (${ENV_NAME}, ${SCOPE}) ===${NC}"
echo ""

# Check for required tools
if ! command -v curl &> /dev/null; then
  echo -e "${RED}Error: curl not found${NC}"
  exit 1
fi

# Check for Claude CLI
if ! command -v claude &> /dev/null; then
  echo -e "${YELLOW}Warning: 'claude' CLI not found${NC}"
  CLAUDE_AVAILABLE=false
else
  CLAUDE_AVAILABLE=true
fi

# Check for Codex CLI
if ! command -v codex &> /dev/null; then
  echo -e "${YELLOW}Warning: 'codex' CLI not found${NC}"
  CODEX_AVAILABLE=false
else
  CODEX_AVAILABLE=true
fi

# Set Codex server name (uses underscores for TOML compatibility)
if [[ "$ENV" == "staging" ]]; then
  CODEX_MCP_NAME="watercooler_cloud_staging"
else
  CODEX_MCP_NAME="watercooler_cloud"
fi

# Check if we have at least one CLI available
if [[ "$CLAUDE_AVAILABLE" == false && "$CODEX_AVAILABLE" == false ]]; then
  echo -e "${YELLOW}Neither Claude nor Codex CLI found${NC}"
  echo -e "${YELLOW}Will provide manual configuration instructions instead${NC}"
  echo ""
fi

# Step 1: Open Console Page
echo -e "${CYAN}Step 1: Open Watercooler Console${NC}"
echo ""
echo "Opening console in your browser..."
echo "URL: ${WORKER_URL}/console"
echo ""

# Try to open browser (works on most systems)
if command -v xdg-open &> /dev/null; then
  xdg-open "${WORKER_URL}/console" 2>/dev/null || true
elif command -v open &> /dev/null; then
  open "${WORKER_URL}/console" 2>/dev/null || true
else
  echo -e "${YELLOW}Could not auto-open browser. Please visit manually:${NC}"
  echo "${WORKER_URL}/console"
fi

echo ""
echo -e "${CYAN}Instructions:${NC}"
echo "1. If not logged in, you'll be redirected to GitHub OAuth"
echo "2. After login, you'll see the Watercooler Console"
echo "3. Click 'Create Token' button"
echo "4. Copy the generated Bearer token (it will be displayed in the browser)"
echo ""
echo "Press Enter when you have copied the token..."
read -p "" WAIT_FOR_USER

echo ""
echo -e "${CYAN}Bearer Token:${NC} (paste the token you got from /console)"
read -p "Paste token here: " TOKEN

if [[ -z "$TOKEN" ]]; then
  echo -e "${RED}Error: No token provided${NC}"
  exit 1
fi

echo ""

# Configure MCP server using Claude CLI or show manual instructions
if [[ "$CLAUDE_AVAILABLE" == true ]]; then
  echo -e "${CYAN}Step 2: Configuring Claude MCP Server${NC}"
  echo ""

  # Check if MCP server already exists and remove it
  if claude mcp get "${MCP_NAME}" &>/dev/null; then
    echo -e "${YELLOW}MCP server '${MCP_NAME}' already exists - removing to update with new token...${NC}"
    echo ""

    if claude mcp remove "${MCP_NAME}"; then
      echo -e "${GREEN}✓ Removed existing server${NC}"
      echo ""
    else
      echo -e "${RED}Failed to remove existing server${NC}"
      echo -e "${YELLOW}You may need to configure manually (see instructions below)${NC}"
      CLAUDE_AVAILABLE=false
    fi
  fi

  if [[ "$CLAUDE_AVAILABLE" == true ]]; then
    echo "Running: claude mcp add --transport stdio ${MCP_NAME} --scope ${SCOPE} -- npx -y mcp-remote \"${SSE_URL}\" --header \"Authorization: Bearer <TOKEN>\" --transport sse-only"
    echo ""

    # Run the claude mcp add command with stdio transport
    if claude mcp add --transport stdio "${MCP_NAME}" --scope "${SCOPE}" -- npx -y mcp-remote "${SSE_URL}" --header "Authorization: Bearer ${TOKEN}" --transport sse-only; then
      echo ""
      echo -e "${GREEN}✓ MCP server '${MCP_NAME}' configured successfully!${NC}"
      echo ""

      if [[ "$SCOPE" == "user" ]]; then
        echo -e "${CYAN}Configuration saved to: ~/.claude.json${NC}"
      else
        echo -e "${CYAN}Configuration saved to: ./.claude.json${NC}"
      fi

      echo ""
      echo -e "${YELLOW}Note: Restart Claude Code to load the new MCP server${NC}"
    else
      echo ""
      echo -e "${RED}Failed to configure MCP server${NC}"
      echo -e "${YELLOW}You may need to configure manually (see instructions below)${NC}"
      CLAUDE_AVAILABLE=false
    fi
  fi
fi

# Configure Codex MCP server if Codex CLI is available
if [[ "$CODEX_AVAILABLE" == true ]]; then
  echo ""
  echo -e "${CYAN}Step 3: Configuring Codex MCP Server${NC}"
  echo ""
  echo -e "${YELLOW}Note: Codex uses global config (~/.codex/config.toml) regardless of scope setting${NC}"
  echo ""

  # Check if MCP server already exists and remove it
  if codex mcp get "${CODEX_MCP_NAME}" &>/dev/null; then
    echo -e "${YELLOW}MCP server '${CODEX_MCP_NAME}' already exists in Codex - removing to update with new token...${NC}"
    echo ""

    if codex mcp remove "${CODEX_MCP_NAME}"; then
      echo -e "${GREEN}✓ Removed existing Codex server${NC}"
      echo ""
    else
      echo -e "${RED}Failed to remove existing Codex server${NC}"
      echo -e "${YELLOW}You may need to configure manually (see instructions below)${NC}"
      CODEX_AVAILABLE=false
    fi
  fi

  if [[ "$CODEX_AVAILABLE" == true ]]; then
    echo "Running: codex mcp add ${CODEX_MCP_NAME} -- npx -y mcp-remote \"${SSE_URL}\" --header \"Authorization: Bearer <TOKEN>\" --transport sse-only"
    echo ""

    # Run the codex mcp add command
    if codex mcp add "${CODEX_MCP_NAME}" -- npx -y mcp-remote "${SSE_URL}" --header "Authorization: Bearer ${TOKEN}" --transport sse-only; then
      echo ""
      echo -e "${GREEN}✓ Codex MCP server '${CODEX_MCP_NAME}' configured successfully!${NC}"
      echo ""
      echo -e "${CYAN}Configuration saved to: ~/.codex/config.toml${NC}"
      echo ""
      echo -e "${YELLOW}Note: Restart Codex to load the new MCP server${NC}"
    else
      echo ""
      echo -e "${RED}Failed to configure Codex MCP server${NC}"
      echo -e "${YELLOW}You may need to configure manually (see instructions below)${NC}"
      CODEX_AVAILABLE=false
    fi
  fi
fi

# Show summary
if [[ "$CLAUDE_AVAILABLE" == true || "$CODEX_AVAILABLE" == true ]]; then
  echo ""
  echo -e "${GREEN}=== Configuration Complete ===${NC}"
  echo ""
  if [[ "$CLAUDE_AVAILABLE" == true ]]; then
    echo -e "${GREEN}✓ Claude CLI configured${NC}"
  fi
  if [[ "$CODEX_AVAILABLE" == true ]]; then
    echo -e "${GREEN}✓ Codex CLI configured${NC}"
  fi
  echo ""
  echo -e "${YELLOW}Remember to restart your IDE(s) to load the new MCP servers${NC}"
  echo ""
fi

# Fallback: Show manual configuration
if [[ "$CLAUDE_AVAILABLE" == false && "$CODEX_AVAILABLE" == false ]]; then
  # Fallback: Show manual configuration
  echo -e "${BLUE}=== Manual Configuration Required ===${NC}"
  echo ""
  echo -e "${CYAN}Option 1: Use Claude CLI (recommended)${NC}"
  echo ""
  echo "Install Claude CLI, then run:"
  echo ""
  echo "  # If ${MCP_NAME} already exists, remove it first:"
  echo "  claude mcp remove ${MCP_NAME}"
  echo ""
  echo "  # Add the new configuration:"
  echo "  claude mcp add --transport stdio ${MCP_NAME} --scope ${SCOPE} -- \\"
  echo "    npx -y mcp-remote \"${SSE_URL}\" \\"
  echo "    --header \"Authorization: Bearer ${TOKEN}\" \\"
  echo "    --transport sse-only"
  echo ""
  echo -e "${CYAN}Option 2: Manual JSON Configuration${NC}"
  echo ""

  if [[ "$SCOPE" == "user" ]]; then
    echo "Edit ~/.claude.json:"
  else
    echo "Edit ./.claude.json (project root):"
  fi

  echo ""
  echo "Remove the old '${MCP_NAME}' entry if it exists, then add:"
  echo ""
  cat <<EOF
{
  "mcpServers": {
    "${MCP_NAME}": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "${SSE_URL}",
        "--header",
        "Authorization: Bearer ${TOKEN}",
        "--transport",
        "sse-only"
      ]
    }
  }
}
EOF
  echo ""
  echo -e "${CYAN}Option 3: Use Codex CLI${NC}"
  echo ""
  echo "Install Codex CLI, then run:"
  echo ""
  echo "  # If ${CODEX_MCP_NAME} already exists, remove it first:"
  echo "  codex mcp remove ${CODEX_MCP_NAME}"
  echo ""
  echo "  # Add the new configuration:"
  echo "  codex mcp add ${CODEX_MCP_NAME} -- \\"
  echo "    npx -y mcp-remote \"${SSE_URL}\" \\"
  echo "    --header \"Authorization: Bearer ${TOKEN}\" \\"
  echo "    --transport sse-only"
  echo ""
  echo -e "${CYAN}Option 4: Manual TOML Configuration (Codex)${NC}"
  echo ""
  echo "Edit ~/.codex/config.toml:"
  echo ""
  echo "Remove the old [mcp_servers.${CODEX_MCP_NAME}] section if it exists, then add:"
  echo ""
  cat <<EOF
[mcp_servers.${CODEX_MCP_NAME}]
command = "npx"
args = [
  "-y",
  "mcp-remote",
  "${SSE_URL}",
  "--header",
  "Authorization: Bearer ${TOKEN}",
  "--transport",
  "sse-only"
]
EOF
fi

echo ""
echo -e "${YELLOW}Note: Token expires in 30 days. Re-run this script to generate a new one.${NC}"
echo ""
