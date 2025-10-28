# Mothballed (Archived) Remote Stack

This directory contains the archived Cloudflare Worker + Remote MCP deployment code and documentation.

The project has moved to a local stdio MCP ("universal dev mode") that resolves the correct threads
repository and branch from per‑call context (code_path) and explicit identity (agent_func). See:

- docs/TESTER_SETUP.md – one‑liner install, required parameters, examples
- docs/LOCAL_QUICKSTART.md – required call parameters and usage discipline
- docs/BRANCH_PAIRING.md – branch pairing contract

Archived from:
- cloudflare-worker/ → .mothballed/cloudflare-worker/
- src/watercooler_mcp/http_facade.py → .mothballed/src/
- tests/test_http_facade_*.py → .mothballed/tests/
- Remote deployment docs under docs/ → .mothballed/docs/
  - CLOUDFLARE_REMOTE_MCP_PLAYBOOK__v1.md
  - Cloudflare_Remote_MCP_Playbook_AUTH_FIRST_PROXY_FIRST__v2.md
  - DEPLOYMENT.md
  - DUAL_STACK_DEPLOYMENT.md
  - NEW_REPO_MIGRATION_AND_DEPLOYMENT.md
  - OPERATOR_RUNBOOK.md
  - PRODUCTION_REPO_SANITIZATION_AND_DEPLOYMENT.md
  - REMOTE_MCP_QUICKSTART.md
  - DEPLOYMENT_QUICK_START.md (moved 2025-10-28)
  - CLOUD_SYNC_STRATEGY.md (moved 2025-10-28)
  - CLOUD_SYNC_GUIDE.md (moved 2025-10-28)
  - CLOUD_SYNC_ARCHITECTURE.md (moved 2025-10-28)

Date archived: 2025-10-28 (UTC)
Reason: remote stack mothballed in favor of a simpler, universal local MCP.

