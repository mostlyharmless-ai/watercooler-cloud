---
name: Reactivation Playbook — watercooler-cloud (remote stack)
about: Checklist to reactivate Cloudflare Worker + Render backend for watercooler-cloud
title: "Reactivation: watercooler-cloud — <staging|production>"
labels: [ops, reactivation, watercooler-cloud]
assignees: []
---

## Summary & Scope
- [ ] Target environment selected: `staging` | `production`
- [ ] Reason for reactivation noted:

## Prerequisites
- [ ] Threads repo exists and has a main branch
  - staging: `mostlyharmless-ai/watercooler-cloud-threads-staging`
  - production: `mostlyharmless-ai/watercooler-cloud-threads`
- [ ] `.gitattributes` includes union merges (`*.md`, `*.jsonl`)
- [ ] Team has access (SSH/PAT) to threads repo

## Render Backend (FastAPI/MCP facade)
- [ ] Scale service up from 0 (or enable instance)
- [ ] Auto-deploy toggled appropriately
- [ ] Env vars present (verify):
  - [ ] `INTERNAL_AUTH_SECRET`
  - [ ] `BASE_THREADS_ROOT=/data/wc-cloud`
  - [ ] `WATERCOOLER_DIR=/data/wc-cloud`
  - [ ] (Optional) `WATERCOOLER_GIT_REPO` + author/email + SSH key if used
- [ ] Deploy latest
- [ ] Health check OK (app logs clean)

## Cloudflare Worker (Auth proxy + SSE)
- [ ] Secrets present (via CF UI or wrangler):
  - [ ] `GITHUB_CLIENT_ID`
  - [ ] `GITHUB_CLIENT_SECRET`
  - [ ] `INTERNAL_AUTH_SECRET` (must match backend)
- [ ] `wrangler.toml` account_id set
- [ ] Deploy Worker
- [ ] Verify:
  - [ ] `GET /health` returns OK
  - [ ] `GET /debug/secrets` shows populated values
  - [ ] `GET /auth/login` redirects with a non-empty `client_id`

## ACL & Access
- [ ] Seed/verify KV ACL entries for initial users/projects (staging may be looser)
- [ ] Confirm 403 for users without allowlist

## Client Configuration (Claude/Codex)
- [ ] Obtain Bearer token (via `/console` UI) for target environment
- [ ] Update MCP server endpoint to remote SSE URL with token
- [ ] Remove/disable local-only config for this test (keep as fallback)

## End-to-End Validation
- [ ] `watercooler_health` OK
- [ ] `watercooler_list_threads` shows threads
- [ ] `watercooler_read_thread` works
- [ ] `watercooler_say` appends entry; git commit appears in threads repo

## Observability & Security
- [ ] Review Worker tail logs for auth flow and denials
- [ ] Review backend logs for MCP calls
- [ ] Confirm no secrets leaked in logs

## Rollback (if needed)
- [ ] Scale Render back to 0; disable auto-deploy
- [ ] Pause Worker redeploys
- [ ] Switch clients back to local MCP + GitHub threads

## Notes / Follow-ups
- [ ] Open issues for any regressions or polish items

