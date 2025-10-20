#!/bin/bash
#
# Configure Cloudflare Worker secrets interactively
#
# Usage:
#   ./scripts/set-secrets.sh
#
# Secrets:
#   GITHUB_CLIENT_ID - Get from: https://github.com/settings/developers
#     Your GitHub OAuth app's Client ID (public identifier)
#
#   GITHUB_CLIENT_SECRET - Get from: https://github.com/settings/developers
#     Your GitHub OAuth app's Client Secret (keep confidential!)
#
#   INTERNAL_AUTH_SECRET - Auto-generated or custom
#     Shared secret for Worker <-> Backend authentication
#     Must be set identically on both Worker (here) and Backend (Render env vars)
#     Minimum 32 characters, cryptographically random
#
# Security Notes:
#   - Secrets are stored encrypted by Cloudflare
#   - Never commit secrets to git
#   - Use different secrets for staging and production
#   - Rotate secrets every 90 days
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

echo -e "${BLUE}=== Cloudflare Worker Secrets Configuration ===${NC}"
echo ""

# Check wrangler
if ! npx wrangler --version &> /dev/null; then
    echo -e "${RED}Error: wrangler not found${NC}"
    echo "Install: npm install"
    exit 1
fi

# Check if logged in
if ! npx wrangler whoami &> /dev/null; then
    echo -e "${YELLOW}Not logged in to Cloudflare.${NC}"
    echo "Run: npx wrangler login"
    exit 1
fi

echo -e "${GREEN}✓ Logged in to Cloudflare${NC}"
echo ""

# Show current secrets (without values)
echo -e "${BLUE}Current secrets:${NC}"
npx wrangler secret list 2>/dev/null || echo "(none)"
echo ""

# Generate secure random secret
generate_secret() {
    # 32 bytes = 64 hex chars
    openssl rand -hex 32 2>/dev/null || \
    head -c 32 /dev/urandom | base64 | tr -d '\n' | head -c 64
}

# Set secret helper
set_secret() {
    local NAME=$1
    local VALUE=$2
    echo "$VALUE" | npx wrangler secret put "$NAME" > /dev/null 2>&1
}

# GitHub Client ID
echo -e "${CYAN}=== GitHub OAuth App Configuration ===${NC}"
echo ""
echo "Get these from: https://github.com/organizations/mostlyharmless-ai/settings/applications"
echo ""
echo "Current OAuth App:"
echo "  - Application name: Watercooler Remote MCP"
echo "  - Homepage URL: https://mharmless-remote-mcp.mostlyharmless-ai.workers.dev/"
echo "  - Callback URL: https://mharmless-remote-mcp.mostlyharmless-ai.workers.dev/auth/callback"
echo ""

read -p "Enter GITHUB_CLIENT_ID: " GITHUB_CLIENT_ID

if [[ -z "$GITHUB_CLIENT_ID" ]]; then
    echo -e "${RED}Error: GITHUB_CLIENT_ID cannot be empty${NC}"
    exit 1
fi

# GitHub Client Secret
echo ""
read -sp "Enter GITHUB_CLIENT_SECRET: " GITHUB_CLIENT_SECRET
echo ""

if [[ -z "$GITHUB_CLIENT_SECRET" ]]; then
    echo -e "${RED}Error: GITHUB_CLIENT_SECRET cannot be empty${NC}"
    exit 1
fi

# Internal Auth Secret
echo ""
echo -e "${CYAN}=== Internal Authentication Secret ===${NC}"
echo ""
echo "This secret authenticates the Worker to the Backend."
echo "It must be set identically on:"
echo "  1. Worker (here)"
echo "  2. Backend (Render environment variables)"
echo ""
echo "Options:"
echo "  1. Auto-generate secure random secret (recommended)"
echo "  2. Enter custom secret (must be 32+ characters)"
echo ""
read -p "Choice (1 or 2): " SECRET_CHOICE

if [[ "$SECRET_CHOICE" == "1" ]]; then
    INTERNAL_AUTH_SECRET=$(generate_secret)
    echo ""
    echo -e "${GREEN}Generated secure random secret${NC}"
elif [[ "$SECRET_CHOICE" == "2" ]]; then
    echo ""
    read -sp "Enter INTERNAL_AUTH_SECRET (32+ chars): " INTERNAL_AUTH_SECRET
    echo ""

    if [[ ${#INTERNAL_AUTH_SECRET} -lt 32 ]]; then
        echo -e "${RED}Error: Secret must be at least 32 characters${NC}"
        exit 1
    fi
else
    echo -e "${RED}Invalid choice${NC}"
    exit 1
fi

# Confirm
echo ""
echo -e "${YELLOW}=== Confirm Configuration ===${NC}"
echo ""
echo "GITHUB_CLIENT_ID: $GITHUB_CLIENT_ID"
echo "GITHUB_CLIENT_SECRET: ${GITHUB_CLIENT_SECRET:0:4}...${GITHUB_CLIENT_SECRET: -4}"
echo "INTERNAL_AUTH_SECRET: ${INTERNAL_AUTH_SECRET:0:8}...${INTERNAL_AUTH_SECRET: -8}"
echo ""
read -p "Set these secrets? (yes/no): " CONFIRM

if [[ "$CONFIRM" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

# Set secrets
echo ""
echo -e "${BLUE}Setting secrets...${NC}"

echo "Setting GITHUB_CLIENT_ID..."
set_secret "GITHUB_CLIENT_ID" "$GITHUB_CLIENT_ID"
echo -e "${GREEN}✓ GITHUB_CLIENT_ID set${NC}"

echo "Setting GITHUB_CLIENT_SECRET..."
set_secret "GITHUB_CLIENT_SECRET" "$GITHUB_CLIENT_SECRET"
echo -e "${GREEN}✓ GITHUB_CLIENT_SECRET set${NC}"

echo "Setting INTERNAL_AUTH_SECRET..."
set_secret "INTERNAL_AUTH_SECRET" "$INTERNAL_AUTH_SECRET"
echo -e "${GREEN}✓ INTERNAL_AUTH_SECRET set${NC}"

# Success
echo ""
echo -e "${GREEN}=== Secrets configured successfully! ===${NC}"
echo ""

# Save INTERNAL_AUTH_SECRET to clipboard or file
echo -e "${YELLOW}IMPORTANT: Copy INTERNAL_AUTH_SECRET to Backend${NC}"
echo ""
echo "You must set this EXACT value on your Render backend:"
echo ""
echo -e "${CYAN}INTERNAL_AUTH_SECRET=${INTERNAL_AUTH_SECRET}${NC}"
echo ""
echo "Steps for Render:"
echo "  1. Go to: https://dashboard.render.com"
echo "  2. Select your watercooler backend service"
echo "  3. Go to: Environment"
echo "  4. Add environment variable:"
echo "       Name: INTERNAL_AUTH_SECRET"
echo "       Value: (paste the value above)"
echo "  5. Save (this will redeploy the backend)"
echo ""

# Offer to save to file
read -p "Save INTERNAL_AUTH_SECRET to .internal-auth-secret file? (yes/no): " SAVE_FILE

if [[ "$SAVE_FILE" == "yes" ]]; then
    echo "$INTERNAL_AUTH_SECRET" > .internal-auth-secret
    chmod 600 .internal-auth-secret
    echo -e "${GREEN}✓ Saved to .internal-auth-secret (git-ignored)${NC}"
    echo ""
fi

echo "Next steps:"
echo "  1. Configure INTERNAL_AUTH_SECRET on Render backend"
echo "  2. Create KV namespace (if not done):"
echo "       npx wrangler kv namespace create \"KV_PROJECTS\""
echo "  3. Deploy the worker:"
echo "       ./scripts/deploy.sh staging"
echo ""
