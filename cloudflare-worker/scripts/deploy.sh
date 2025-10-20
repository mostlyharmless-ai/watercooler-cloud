#!/bin/bash
#
# Deploy Cloudflare Worker with pre-flight security checks
#
# Usage:
#   ./scripts/deploy.sh [staging|production]
#
# Environment Variables (set in wrangler.toml):
#   BACKEND_URL - FastAPI backend URL (e.g. https://watercooler.onrender.com)
#   DEFAULT_AGENT - Default agent name (e.g. "Claude")
#   ALLOW_DEV_SESSION - Set to "true" for staging only (enables ?session=dev)
#
# Secrets (set via wrangler secret put):
#   GITHUB_CLIENT_ID - GitHub OAuth app client ID
#   GITHUB_CLIENT_SECRET - GitHub OAuth app secret
#   INTERNAL_AUTH_SECRET - Shared secret for Worker <-> Backend auth (32+ chars)
#
# KV Binding (configured in wrangler.toml):
#   KV_PROJECTS - Namespace for sessions, ACLs, OAuth state, rate limits
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Change to worker directory
cd "$(dirname "$0")/.." || exit 1

# Parse environment argument
ENV="${1:-staging}"
if [[ "$ENV" != "staging" && "$ENV" != "production" ]]; then
    echo -e "${RED}Error: Environment must be 'staging' or 'production'${NC}"
    echo "Usage: $0 [staging|production]"
    exit 1
fi

echo -e "${BLUE}=== Cloudflare Worker Deployment ===${NC}"
echo -e "Environment: ${GREEN}$ENV${NC}"
echo ""

# Pre-flight checks
echo -e "${BLUE}Running pre-flight checks...${NC}"

# Check if wrangler is installed (in node_modules)
if ! npx wrangler --version &> /dev/null; then
    echo -e "${RED}✗ wrangler not found${NC}"
    echo "Install: npm install"
    exit 1
fi
echo -e "${GREEN}✓ wrangler installed${NC}"

# Check if wrangler.toml exists
if [[ ! -f "wrangler.toml" ]]; then
    echo -e "${RED}✗ wrangler.toml not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ wrangler.toml found${NC}"

# Check secrets
echo ""
echo -e "${BLUE}Checking required secrets...${NC}"

REQUIRED_SECRETS=("GITHUB_CLIENT_ID" "GITHUB_CLIENT_SECRET" "INTERNAL_AUTH_SECRET")
MISSING_SECRETS=()

for SECRET in "${REQUIRED_SECRETS[@]}"; do
    if npx wrangler secret list 2>/dev/null | grep -q "^$SECRET"; then
        echo -e "${GREEN}✓ $SECRET is set${NC}"
    else
        echo -e "${RED}✗ $SECRET is missing${NC}"
        MISSING_SECRETS+=("$SECRET")
    fi
done

if [[ ${#MISSING_SECRETS[@]} -gt 0 ]]; then
    echo ""
    echo -e "${RED}Missing secrets detected!${NC}"
    echo "Run: ./scripts/set-secrets.sh to configure secrets"
    exit 1
fi

# Check KV namespace binding
echo ""
echo -e "${BLUE}Checking KV namespace binding...${NC}"

if grep -q "binding = \"KV_PROJECTS\"" wrangler.toml; then
    KV_ID=$(grep -A 3 "binding = \"KV_PROJECTS\"" wrangler.toml | grep "^id = " | cut -d'"' -f2 || echo "")
    if [[ -n "$KV_ID" ]]; then
        echo -e "${GREEN}✓ KV_PROJECTS bound (ID: $KV_ID)${NC}"
    else
        echo -e "${YELLOW}⚠ KV_PROJECTS binding found but ID unclear${NC}"
    fi
else
    echo -e "${RED}✗ KV_PROJECTS binding missing in wrangler.toml${NC}"
    echo ""
    echo "Create KV namespace:"
    echo "  wrangler kv:namespace create \"KV_PROJECTS\""
    echo "  wrangler kv:namespace create \"KV_PROJECTS\" --preview"
    echo ""
    echo "Then add to wrangler.toml:"
    echo "  [[kv_namespaces]]"
    echo "  binding = \"KV_PROJECTS\""
    echo "  id = \"<namespace_id>\""
    echo "  preview_id = \"<preview_namespace_id>\""
    exit 1
fi

# Check environment-specific config
echo ""
echo -e "${BLUE}Checking environment configuration...${NC}"

if [[ "$ENV" == "production" ]]; then
    # Production checks
    if grep -q "ALLOW_DEV_SESSION.*=.*true" wrangler.toml | grep -v "^#"; then
        echo -e "${RED}✗ ALLOW_DEV_SESSION is enabled${NC}"
        echo ""
        echo -e "${RED}SECURITY RISK: Dev session is enabled in production!${NC}"
        echo "Remove or comment out ALLOW_DEV_SESSION in wrangler.toml [env.production]"
        exit 1
    fi
    echo -e "${GREEN}✓ ALLOW_DEV_SESSION is disabled${NC}"

    # Warn about production deployment
    echo ""
    echo -e "${YELLOW}⚠ You are about to deploy to PRODUCTION${NC}"
    echo "This will affect live users."
    echo ""
    read -p "Continue? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Deployment cancelled."
        exit 0
    fi

else
    # Staging checks
    if ! grep -q "ALLOW_DEV_SESSION.*=.*\"true\"" wrangler.toml; then
        echo -e "${YELLOW}⚠ ALLOW_DEV_SESSION not explicitly set to \"true\"${NC}"
        echo "You may want to enable dev session for staging testing."
        echo "Add to wrangler.toml [env.staging]:"
        echo "  ALLOW_DEV_SESSION = \"true\""
    else
        echo -e "${GREEN}✓ ALLOW_DEV_SESSION enabled (staging)${NC}"
    fi
fi

# Check backend URL
if ! grep -q "BACKEND_URL" wrangler.toml; then
    echo -e "${YELLOW}⚠ BACKEND_URL not found in wrangler.toml${NC}"
    echo "You may need to add:"
    echo "  BACKEND_URL = \"https://watercooler.onrender.com\""
fi

# All checks passed
echo ""
echo -e "${GREEN}=== All pre-flight checks passed ===${NC}"
echo ""

# Note: No separate build step needed - wrangler handles TypeScript compilation

# Deploy
echo -e "${BLUE}Deploying to $ENV...${NC}"
if [[ "$ENV" == "production" ]]; then
    npx wrangler deploy
else
    npx wrangler deploy --env "$ENV"
fi

# Success
echo ""
echo -e "${GREEN}=== Deployment successful! ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Test OAuth flow:"
echo "     Visit: https://mharmless-remote-mcp${ENV:+-$ENV}.mostlyharmless-ai.workers.dev/auth/login"
echo ""
echo "  2. Monitor logs:"
echo "     ./scripts/tail-logs.sh auth"
echo ""
echo "  3. Seed ACL data (if not already done):"
echo "     ./scripts/seed-acl.sh <github-login> <project-name>"
echo ""
echo "  4. Run security tests:"
echo "     ./scripts/test-security.sh https://mharmless-remote-mcp${ENV:+-$ENV}.mostlyharmless-ai.workers.dev"
echo ""
