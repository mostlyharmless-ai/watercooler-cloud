#!/bin/bash
#
# Seed or update KV ACL (Access Control List) for a user
#
# Usage:
#   ./scripts/seed-acl.sh <github-login> <project1> [project2] [project3] ...
#
# Examples:
#   # Grant user 'octocat' access to 'proj-alpha'
#   ./scripts/seed-acl.sh octocat proj-alpha
#
#   # Grant user 'octocat' access to multiple projects
#   ./scripts/seed-acl.sh octocat proj-alpha proj-beta proj-gamma
#
#   # View current ACL for user
#   ./scripts/seed-acl.sh octocat --show
#
#   # Remove user's ACL (revoke all access)
#   ./scripts/seed-acl.sh octocat --remove
#
# ACL Schema:
#   KV Key: user:gh:<github-login>
#   Value: { "projects": ["proj-alpha", "proj-beta"] }
#
# Security Model:
#   - Default-Deny: Users without ACL entry cannot access ANY project
#   - Allowlist: Users can only access projects in their explicit list
#   - To grant access: Add project to list
#   - To revoke access: Remove project from list or delete ACL entry
#
# KV Namespace:
#   Uses KV_PROJECTS binding from wrangler.toml
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Change to worker directory
cd "$(dirname "$0")/.." || exit 1

# Check wrangler
if ! npx wrangler --version &> /dev/null; then
    echo -e "${RED}Error: wrangler not found${NC}"
    echo "Install: npm install"
    exit 1
fi

# Get KV namespace ID from wrangler.toml
get_kv_namespace_id() {
    grep -A 3 'binding = "KV_PROJECTS"' wrangler.toml | grep "^id = " | head -1 | cut -d'"' -f2
}

KV_NAMESPACE_ID=$(get_kv_namespace_id)

if [[ -z "$KV_NAMESPACE_ID" ]]; then
    echo -e "${RED}Error: KV_PROJECTS namespace not found in wrangler.toml${NC}"
    echo ""
    echo "Create namespace:"
    echo "  npx wrangler kv namespace create \"KV_PROJECTS\""
    echo ""
    echo "Add to wrangler.toml:"
    echo "  [[kv_namespaces]]"
    echo "  binding = \"KV_PROJECTS\""
    echo "  id = \"<namespace_id>\""
    exit 1
fi

# Parse arguments
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <github-login> <project1> [project2] [project3] ..."
    echo ""
    echo "Examples:"
    echo "  $0 octocat proj-alpha"
    echo "  $0 octocat proj-alpha proj-beta"
    echo "  $0 octocat --show"
    echo "  $0 octocat --remove"
    exit 1
fi

GITHUB_LOGIN=$1
shift

KV_KEY="user:gh:${GITHUB_LOGIN}"

# Show existing ACL
show_acl() {
    echo -e "${BLUE}Fetching ACL for user: ${CYAN}${GITHUB_LOGIN}${NC}"
    echo -e "${BLUE}KV Key: ${CYAN}${KV_KEY}${NC}"
    echo ""

    VALUE=$(npx wrangler kv key get "$KV_KEY" --binding=KV_PROJECTS --remote 2>/dev/null || echo "")

    if [[ -z "$VALUE" ]]; then
        echo -e "${YELLOW}No ACL found for this user${NC}"
        echo "User has NO access to any projects (default-deny)"
    else
        echo -e "${GREEN}Current ACL:${NC}"
        echo "$VALUE" | jq . 2>/dev/null || echo "$VALUE"
    fi
    echo ""
}

# Remove ACL
remove_acl() {
    echo -e "${YELLOW}Removing ACL for user: ${CYAN}${GITHUB_LOGIN}${NC}"
    echo -e "${YELLOW}This will REVOKE ALL project access for this user.${NC}"
    echo ""
    read -p "Continue? (yes/no): " CONFIRM

    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Cancelled."
        exit 0
    fi

    npx wrangler kv key delete "$KV_KEY" --binding=KV_PROJECTS --remote 2>/dev/null || true
    echo -e "${GREEN}✓ ACL removed${NC}"
    echo ""
    echo "User ${GITHUB_LOGIN} now has NO access to any projects."
}

# Handle special flags
if [[ $# -eq 1 && "$1" == "--show" ]]; then
    show_acl
    exit 0
fi

if [[ $# -eq 1 && "$1" == "--remove" ]]; then
    remove_acl
    exit 0
fi

# Validate projects
if [[ $# -lt 1 ]]; then
    echo -e "${RED}Error: No projects specified${NC}"
    echo "Usage: $0 $GITHUB_LOGIN <project1> [project2] ..."
    exit 1
fi

PROJECTS=("$@")

# Show operation
echo -e "${BLUE}=== ACL Configuration ===${NC}"
echo ""
echo -e "GitHub User: ${CYAN}${GITHUB_LOGIN}${NC}"
echo -e "KV Key: ${CYAN}${KV_KEY}${NC}"
echo -e "Projects: ${GREEN}${PROJECTS[*]}${NC}"
echo ""

# Check if ACL already exists
EXISTING_VALUE=$(npx wrangler kv key get "$KV_KEY" --binding=KV_PROJECTS --remote 2>/dev/null || echo "")

if [[ -n "$EXISTING_VALUE" ]]; then
    echo -e "${YELLOW}⚠ User already has ACL:${NC}"
    echo "$EXISTING_VALUE" | jq . 2>/dev/null || echo "$EXISTING_VALUE"
    echo ""
    echo -e "${YELLOW}This will REPLACE the existing ACL.${NC}"
    echo ""
fi

# Confirm
read -p "Create/update ACL? (yes/no): " CONFIRM

if [[ "$CONFIRM" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

# Build JSON
PROJECTS_JSON=$(printf '%s\n' "${PROJECTS[@]}" | jq -R . | jq -s .)
ACL_JSON=$(jq -n --argjson projects "$PROJECTS_JSON" '{projects: $projects}')

# Write to KV
echo ""
echo -e "${BLUE}Writing to KV...${NC}"
npx wrangler kv key put "$KV_KEY" "$ACL_JSON" --binding=KV_PROJECTS --remote

echo -e "${GREEN}✓ ACL configured successfully${NC}"
echo ""

# Verify
echo -e "${BLUE}Verifying...${NC}"
show_acl

# Success message
echo -e "${GREEN}=== ACL Update Complete ===${NC}"
echo ""
echo "User ${CYAN}${GITHUB_LOGIN}${NC} can now access:"
for PROJECT in "${PROJECTS[@]}"; do
    echo -e "  ${GREEN}✓${NC} $PROJECT"
done
echo ""
echo "Test access:"
echo "  1. Authenticate: https://your-worker.dev/auth/login"
echo "  2. Connect MCP client with project parameter:"
echo "       ?project=${PROJECTS[0]}"
echo ""

# Show deny example
if [[ ${#PROJECTS[@]} -gt 0 ]]; then
    echo "Access is DENIED for any project not in this list (default-deny)."
fi
