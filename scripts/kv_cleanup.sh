#!/bin/bash
# KV Cleanup Script - Remove invalid project entries from user ACLs
#
# Usage: ./kv_cleanup.sh [staging|production] <user-id> <project-to-remove>
#
# Example: ./kv_cleanup.sh staging user:gh:caleb watercooler-collab

set -e

ENV="${1}"
USER_KEY="${2}"
PROJECT_TO_REMOVE="${3}"

if [ -z "$ENV" ] || [ -z "$USER_KEY" ] || [ -z "$PROJECT_TO_REMOVE" ]; then
    echo "Usage: $0 [staging|production] <user-key> <project-to-remove>"
    echo ""
    echo "Examples:"
    echo "  $0 staging user:gh:caleb watercooler-collab"
    echo "  $0 production user:gh:jay watercooler"
    echo ""
    echo "This will:"
    echo "  1. Fetch the user's ACL from KV"
    echo "  2. Remove the specified project from their projects list"
    echo "  3. Update the default project if it was the one being removed"
    echo "  4. Write the cleaned ACL back to KV"
    exit 1
fi

if [ "$ENV" != "staging" ] && [ "$ENV" != "production" ]; then
    echo "Error: Environment must be 'staging' or 'production'"
    exit 1
fi

# Get KV namespace ID from wrangler.toml
KV_ID=$(grep -A 5 "\[env.$ENV.kv_namespaces\]" ../cloudflare-worker/wrangler.toml | grep "id =" | cut -d'"' -f2)

if [ -z "$KV_ID" ]; then
    echo "Error: Could not find KV namespace ID for env '$ENV'"
    exit 1
fi

echo "🧹 KV Cleanup Tool"
echo "Environment: $ENV"
echo "KV Namespace: $KV_ID"
echo "User: $USER_KEY"
echo "Removing project: $PROJECT_TO_REMOVE"
echo ""

# Fetch current ACL
echo "📥 Fetching current ACL..."
current_acl=$(cd ../cloudflare-worker && wrangler kv:key get --namespace-id="$KV_ID" "$USER_KEY" 2>/dev/null || echo "{}")

if [ "$current_acl" = "{}" ] || [ -z "$current_acl" ]; then
    echo "❌ No ACL found for user $USER_KEY"
    exit 1
fi

echo "Current ACL:"
echo "$current_acl" | python3 -m json.tool
echo ""

# Clean the ACL
echo "🔧 Removing project '$PROJECT_TO_REMOVE'..."
cleaned_acl=$(echo "$current_acl" | python3 -c "
import sys, json
acl = json.load(sys.stdin)
project_to_remove = '$PROJECT_TO_REMOVE'

# Remove from projects list
if 'projects' in acl and project_to_remove in acl['projects']:
    acl['projects'].remove(project_to_remove)
    print(f'Removed {project_to_remove} from projects list', file=sys.stderr)

# Update default if it was the removed project
if acl.get('default') == project_to_remove:
    if acl.get('projects'):
        acl['default'] = acl['projects'][0]
        print(f'Updated default to {acl[\"default\"]}', file=sys.stderr)
    else:
        acl['default'] = None
        print('No projects remaining, default set to null', file=sys.stderr)

print(json.dumps(acl, indent=2))
")

echo ""
echo "Cleaned ACL:"
echo "$cleaned_acl" | python3 -m json.tool
echo ""

# Confirm before writing
read -p "Write this cleaned ACL back to KV? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Write back to KV
echo "💾 Writing cleaned ACL..."
echo "$cleaned_acl" | cd ../cloudflare-worker && wrangler kv:key put --namespace-id="$KV_ID" "$USER_KEY" --path=-

echo "✅ Done! Project '$PROJECT_TO_REMOVE' removed from $USER_KEY"
