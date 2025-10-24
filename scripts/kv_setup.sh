#!/bin/bash
# KV Setup Script - Load project ACLs into Cloudflare KV

set -e

echo "Setting up Cloudflare KV for Watercooler Remote MCP..."

# Create KV namespace if it doesn't exist
echo "Creating KV namespace..."
KV_ID=$(wrangler kv:namespace create KV_PROJECTS --preview false 2>&1 | grep -oP 'id = "\K[^"]+')

if [ -z "$KV_ID" ]; then
    echo "Error: Failed to create KV namespace"
    exit 1
fi

echo "KV namespace created with ID: $KV_ID"
echo "Update wrangler.toml with this ID"

# Load seed data
echo ""
echo "Loading seed data from kv_seed_projects.json..."

# Parse JSON and load each entry
cat kv_seed_projects.json | jq -r '.entries[] | @json "wrangler kv:key put --namespace-id='$KV_ID' \(.key | @sh) \(.value | @json | @sh)"' | while read cmd; do
    eval $cmd
    echo "  ✓ Loaded: $(echo $cmd | grep -oP "put.*?'([^']+)'" | cut -d"'" -f2)"
done

echo ""
echo "KV setup complete!"
echo ""
echo "Next steps:"
echo "1. Update cloudflare-worker/wrangler.toml with KV ID: $KV_ID"
echo "2. Set secrets:"
echo "   wrangler secret put GITHUB_CLIENT_ID"
echo "   wrangler secret put GITHUB_CLIENT_SECRET"
echo "   wrangler secret put INTERNAL_AUTH_SECRET"
echo "3. Deploy: cd cloudflare-worker && wrangler deploy"
