#!/bin/bash
# Discover Projects - Query backend for actual project directories
#
# Usage: ./discover_projects.sh [staging|production]

set -e

ENV="${1:-staging}"

if [ "$ENV" = "staging" ]; then
    BACKEND_URL="https://watercooler-collab.onrender.com"
elif [ "$ENV" = "production" ]; then
    BACKEND_URL="https://watercooler-collab.onrender.com"
else
    echo "Usage: $0 [staging|production]"
    exit 1
fi

echo "🔍 Discovering projects on $ENV backend..."
echo "Backend: $BACKEND_URL"
echo ""

# Read INTERNAL_AUTH_SECRET from wrangler secrets or env
if [ -z "$INTERNAL_AUTH_SECRET" ]; then
    echo "⚠️  INTERNAL_AUTH_SECRET not set in environment"
    echo "Please set it before running:"
    echo "  export INTERNAL_AUTH_SECRET='your-secret-here'"
    exit 1
fi

# Call the discover-projects endpoint
response=$(curl -s -X POST "$BACKEND_URL/admin/discover-projects" \
    -H "X-Internal-Auth: $INTERNAL_AUTH_SECRET" \
    -H "Content-Type: application/json")

# Pretty print the response
echo "$response" | python3 -m json.tool

echo ""
echo "---"
echo ""
echo "📊 Summary:"
echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
summary = data.get('summary', {})
print(f\"Total users: {summary.get('total_users', 0)}\")
print(f\"Total projects: {summary.get('total_projects', 0)}\")
print(f\"Projects with thread data: {summary.get('projects_with_data', 0)}\")
print(f\"Empty projects (candidates for cleanup): {summary.get('empty_projects', 0)}\")
print()
print('Projects by user:')
for user, projects in data.get('projects_by_user', {}).items():
    print(f\"  {user}:\")
    for p in projects:
        status = '✓' if p['has_threads'] else '✗'
        print(f\"    {status} {p['project_id']} ({p['thread_count']} threads)\")
"

echo ""
echo "💡 Next steps:"
echo "1. Review empty projects above - they may be artifacts"
echo "2. Use scripts/kv_cleanup.sh to remove invalid ACL entries"
echo "3. Reseed KV with corrected project list using scripts/kv_setup.sh"
