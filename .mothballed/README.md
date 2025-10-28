# Mothballed (Archived) Remote Stack

This directory contains the archived Cloudflare Worker + Remote MCP deployment code and documentation.

The project has moved to a local stdio MCP ("universal dev mode") that resolves the correct threads
repository and branch from per‑call context (code_path) and explicit identity (agent_func). See:

- docs/TESTER_SETUP.md – one‑liner install, required parameters, examples
- docs/LOCAL_QUICKSTART.md – required call parameters and usage discipline
- docs/BRANCH_PAIRING.md – branch pairing contract

Archived from:
- cloudflare-worker/ → .mothballed/cloudflare-worker/
- Remote deployment docs under docs/ → .mothballed/docs/

Date archived: $(date -u +%Y-%m-%d) (UTC)
Reason: remote stack mothballed in favor of a simpler, universal local MCP.

