#!/bin/bash
#
# Stream Cloudflare Worker logs with helpful filters
#
# Usage:
#   ./scripts/tail-logs.sh [filter]
#
# Filters:
#   auth     - Authentication and OAuth events
#   acl      - ACL (access control) decisions
#   session  - Session lifecycle events
#   error    - Errors and failures
#   security - All security-related events
#   all      - Everything (default)
#
# Examples:
#   ./scripts/tail-logs.sh auth
#   ./scripts/tail-logs.sh acl
#   ./scripts/tail-logs.sh error
#   ./scripts/tail-logs.sh
#
# Log Event Types:
#   oauth_login_initiated  - User started OAuth flow
#   auth_success          - Authentication succeeded
#   auth_failure          - Authentication failed
#   session_validated     - Session cookie validated
#   session_invalid       - Invalid/expired session
#   acl_denied           - Project access denied
#   rate_limit_exceeded  - Too many requests
#   dev_session_used     - Dev session bypass used
#   dev_session_rejected - Dev session attempted but disabled
#
# Output Format:
#   Logs are JSON-formatted with:
#   - event: Event type
#   - timestamp: ISO 8601 timestamp
#   - user/ip: User identifier or IP address
#   - Additional context fields
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Change to worker directory
cd "$(dirname "$0")/.." || exit 1

# Check wrangler
if ! npx wrangler --version &> /dev/null; then
    echo -e "${RED}Error: wrangler not found${NC}"
    echo "Install: npm install"
    exit 1
fi

# Parse filter
FILTER="${1:-all}"

# Build filter expression based on type
case "$FILTER" in
    auth)
        echo -e "${BLUE}=== Filtering: Authentication Events ===${NC}"
        SEARCH_TERMS="oauth_login_initiated|auth_success|auth_failure"
        ;;
    acl)
        echo -e "${BLUE}=== Filtering: ACL Events ===${NC}"
        SEARCH_TERMS="acl_denied|acl_allow"
        ;;
    session)
        echo -e "${BLUE}=== Filtering: Session Events ===${NC}"
        SEARCH_TERMS="session_validated|session_invalid|session_expired"
        ;;
    error)
        echo -e "${BLUE}=== Filtering: Errors ===${NC}"
        SEARCH_TERMS="error|failure|invalid|denied|exceeded"
        ;;
    security)
        echo -e "${BLUE}=== Filtering: Security Events ===${NC}"
        SEARCH_TERMS="auth|acl|rate_limit|csrf|session"
        ;;
    all)
        echo -e "${BLUE}=== Showing All Logs ===${NC}"
        SEARCH_TERMS=""
        ;;
    *)
        echo -e "${RED}Error: Unknown filter '$FILTER'${NC}"
        echo ""
        echo "Available filters:"
        echo "  auth     - Authentication and OAuth"
        echo "  acl      - Access control decisions"
        echo "  session  - Session lifecycle"
        echo "  error    - Errors and failures"
        echo "  security - All security events"
        echo "  all      - Everything"
        exit 1
        ;;
esac

echo -e "${CYAN}Press Ctrl+C to stop${NC}"
echo ""

# Helper to colorize logs
colorize_log() {
    while IFS= read -r line; do
        # Try to parse as JSON
        if echo "$line" | jq -e . > /dev/null 2>&1; then
            EVENT=$(echo "$line" | jq -r '.event // empty')

            # Color based on event type
            case "$EVENT" in
                *success*)
                    echo -e "${GREEN}$line${NC}"
                    ;;
                *denied*|*forbidden*|*invalid*|*failure*|*error*)
                    echo -e "${RED}$line${NC}"
                    ;;
                *warning*|*exceeded*|dev_session*)
                    echo -e "${YELLOW}$line${NC}"
                    ;;
                oauth_login_initiated|auth_*)
                    echo -e "${BLUE}$line${NC}"
                    ;;
                acl_*)
                    echo -e "${MAGENTA}$line${NC}"
                    ;;
                session_*)
                    echo -e "${CYAN}$line${NC}"
                    ;;
                *)
                    echo "$line"
                    ;;
            esac
        else
            # Non-JSON log
            echo "$line"
        fi
    done
}

# Tail logs
if [[ -n "$SEARCH_TERMS" ]]; then
    # With filter
    npx wrangler tail --format pretty 2>&1 | grep -E "$SEARCH_TERMS" | colorize_log
else
    # No filter
    npx wrangler tail --format pretty 2>&1 | colorize_log
fi
