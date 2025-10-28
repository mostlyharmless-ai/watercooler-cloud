#!/bin/bash
#
# Security validation tests for OAuth + ACL implementation
#
# Usage:
#   ./scripts/test-security.sh [worker-url]
#
# Example:
#   ./scripts/test-security.sh https://mharmless-remote-mcp-staging.mostlyharmless-ai.workers.dev
#
# Tests:
#   C1: CSRF protection (state parameter validation)
#   C2: Session fixation prevention (cookie-only validation)
#   C3: Rate limiting (OAuth callback throttling)
#   H2: ACL default-deny (require explicit allowlist)
#
# Requirements:
#   - curl
#   - jq (optional, for prettier output)
#
# Note: These tests validate DENIAL scenarios (security working correctly).
#       For positive tests (OAuth flow, ACL allow), use manual browser testing.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Check dependencies
if ! command -v curl &> /dev/null; then
    echo -e "${RED}Error: curl not found${NC}"
    exit 1
fi

# Parse worker URL
WORKER_URL="${1:-}"

if [[ -z "$WORKER_URL" ]]; then
    echo "Usage: $0 <worker-url>"
    echo ""
    echo "Example:"
    echo "  $0 https://mharmless-remote-mcp-staging.mostlyharmless-ai.workers.dev"
    exit 1
fi

# Remove trailing slash
WORKER_URL="${WORKER_URL%/}"

echo -e "${BLUE}=== Security Validation Tests ===${NC}"
echo -e "Worker URL: ${CYAN}${WORKER_URL}${NC}"
echo ""

PASSED=0
FAILED=0

# Test helper
run_test() {
    local NAME=$1
    local EXPECTED_STATUS=$2
    local URL=$3
    shift 3
    local CURL_ARGS=("$@")

    echo -e "${BLUE}Test: ${NAME}${NC}"

    RESPONSE=$(curl -s -w "\n%{http_code}" "${CURL_ARGS[@]}" "$URL" || echo "0")
    BODY=$(echo "$RESPONSE" | head -n -1)
    STATUS=$(echo "$RESPONSE" | tail -n 1)

    if [[ "$STATUS" == "$EXPECTED_STATUS" ]]; then
        echo -e "${GREEN}✓ PASS${NC} - HTTP $STATUS (expected)"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC} - HTTP $STATUS (expected $EXPECTED_STATUS)"
        echo "Response: $BODY"
        ((FAILED++))
    fi
    echo ""
}

# Test C1: CSRF Protection
echo -e "${CYAN}=== C1: CSRF Protection Tests ===${NC}"
echo ""

echo -e "${YELLOW}These tests should FAIL (return 400/403) to prove CSRF protection works${NC}"
echo ""

# Test 1: Callback without state parameter
run_test \
    "C1.1 - OAuth callback without state (should be rejected)" \
    "400" \
    "${WORKER_URL}/auth/callback?code=fake_code"

# Test 2: Callback with invalid state
run_test \
    "C1.2 - OAuth callback with invalid state (should be rejected)" \
    "400" \
    "${WORKER_URL}/auth/callback?code=fake_code&state=invalid_state_12345"

# Test 3: Callback with state but no cookie
run_test \
    "C1.3 - OAuth callback with state but missing cookie (should be rejected)" \
    "400" \
    "${WORKER_URL}/auth/callback?code=fake_code&state=valid_looking_state" \
    -H "Cookie: "

echo -e "${CYAN}=== C2: Session Fixation Prevention Tests ===${NC}"
echo ""

echo -e "${YELLOW}These tests should FAIL (return 401/403) to prove session fixation protection works${NC}"
echo ""

# Test 4: SSE with query param session (no cookie)
run_test \
    "C2.1 - SSE with query param session UUID (should be rejected)" \
    "401" \
    "${WORKER_URL}/sse?project=test-proj&session=fake-uuid-12345"

# Note: Dev session test depends on ALLOW_DEV_SESSION setting
echo -e "${BLUE}Note: C2.2 (dev session) depends on ALLOW_DEV_SESSION setting${NC}"
echo -e "  If ALLOW_DEV_SESSION=true (staging): ?session=dev allowed with warning"
echo -e "  If ALLOW_DEV_SESSION=false (prod): ?session=dev rejected with 401"
echo ""

# Test C3: Rate Limiting
echo -e "${CYAN}=== C3: Rate Limiting Tests ===${NC}"
echo ""

echo -e "${YELLOW}Triggering rate limit (10 requests in 5 minutes)${NC}"
echo -e "${YELLOW}After 10 attempts, should return 429${NC}"
echo ""

RATE_LIMIT_HIT=false
for i in {1..12}; do
    RESPONSE=$(curl -s -w "\n%{http_code}" \
        "${WORKER_URL}/auth/callback?code=rate_test_$i" \
        2>/dev/null || echo "0")
    STATUS=$(echo "$RESPONSE" | tail -n 1)

    if [[ "$STATUS" == "429" ]]; then
        echo -e "${GREEN}✓ Rate limit triggered at attempt $i (HTTP 429)${NC}"
        RATE_LIMIT_HIT=true
        ((PASSED++))
        break
    elif [[ "$STATUS" == "400" ]]; then
        echo -e "  Attempt $i: HTTP 400 (invalid request, expected)"
    else
        echo -e "  Attempt $i: HTTP $STATUS"
    fi

    # Small delay to avoid overloading
    sleep 0.2
done

if [[ "$RATE_LIMIT_HIT" == false ]]; then
    echo -e "${RED}✗ FAIL - Rate limit not triggered after 12 attempts${NC}"
    ((FAILED++))
fi
echo ""

# Test H2: ACL Default-Deny
echo -e "${CYAN}=== H2: ACL Default-Deny Tests ===${NC}"
echo ""

echo -e "${YELLOW}Note: These tests require authentication (session cookie)${NC}"
echo -e "${YELLOW}Skipping automated ACL tests - require manual testing${NC}"
echo ""
echo "Manual ACL test procedure:"
echo "  1. Authenticate via /auth/login"
echo "  2. Try to access project NOT in your ACL allowlist"
echo "  3. Should receive: HTTP 403 + 'Access denied'"
echo "  4. Check logs for: {event: 'acl_denied', reason: '...'}"
echo ""

# Health check
echo -e "${CYAN}=== Health Check ===${NC}"
echo ""

run_test \
    "Worker health endpoint" \
    "200" \
    "${WORKER_URL}/health"

# Summary
echo -e "${BLUE}=== Test Summary ===${NC}"
echo ""
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ All automated security tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Test OAuth flow manually:"
    echo "     Visit: ${WORKER_URL}/auth/login"
    echo ""
    echo "  2. Monitor logs during testing:"
    echo "     ./scripts/tail-logs.sh security"
    echo ""
    echo "  3. Test ACL enforcement manually (see above)"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    echo ""
    echo "Review the failures above and check:"
    echo "  - Worker is deployed and accessible"
    echo "  - Security fixes are deployed (commit af3d47e or later)"
    echo "  - KV namespace is bound and accessible"
    echo ""
    echo "View logs:"
    echo "  ./scripts/tail-logs.sh error"
    echo ""
    exit 1
fi
