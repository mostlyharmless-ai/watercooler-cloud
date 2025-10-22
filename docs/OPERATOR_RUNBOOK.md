# Watercooler Cloud — Operator Runbook (1‑Pager)

This is a concise guide for operators to configure, deploy, test, roll back, and monitor the Watercooler cloud MCP stack (Cloudflare Worker + FastAPI Backend) with OAuth and default‑deny ACLs.

## Environments
- Staging: `ALLOW_DEV_SESSION=true`, OAuth enabled, 2–3 users only
- Production: `ALLOW_DEV_SESSION` unset/false, OAuth required, default‑deny ACLs

## Secrets & Env
- Worker (wrangler secrets): `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `INTERNAL_AUTH_SECRET`
- Worker (wrangler vars): `BACKEND_URL`, `DEFAULT_AGENT`; `ALLOW_DEV_SESSION` (staging only)
- Backend (Render): `INTERNAL_AUTH_SECRET`, `BASE_THREADS_ROOT=/data/wc-cloud`, `WATERCOOLER_DIR=/data/wc-cloud`
- Optional Git: `WATERCOOLER_GIT_REPO`, `WATERCOOLER_GIT_AUTHOR`, `WATERCOOLER_GIT_EMAIL`, `GIT_SSH_PRIVATE_KEY` (PEM)

## Backend Start Command (copy/paste)
Preserve + migrate + initializer (recommended):
```bash
mkdir -p /data/secrets && printf '%s' "$GIT_SSH_PRIVATE_KEY" > /data/secrets/wc_git_key && chmod 600 /data/secrets/wc_git_key && export GIT_SSH_COMMAND="ssh -i /data/secrets/wc_git_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes" && export WATERCOOLER_DIR=/data/wc-cloud BASE_THREADS_ROOT=/data/wc-cloud && if [ -n "$WATERCOOLER_GIT_REPO" ] && [ ! -d /data/wc-cloud/.git ]; then ts=$(date +%s); [ -d /data/wc-cloud ] && mv /data/wc-cloud /data/wc-cloud.bak.$ts || true; git clone "$WATERCOOLER_GIT_REPO" /data/wc-cloud && cd /data/wc-cloud && git config user.name "${WATERCOOLER_GIT_AUTHOR:-Watercooler Bot}" && git config user.email "${WATERCOOLER_GIT_EMAIL:-bot@mostlyharmless.ai}" && if ! git rev-parse --quiet --verify HEAD >/dev/null; then git commit --allow-empty -m "Initialize threads repo" && git push -u origin HEAD || true; fi; if [ -d /data/wc-cloud.bak.$ts ]; then cp -a /data/wc-cloud.bak.$ts/* /data/wc-cloud/ 2>/dev/null || true; git add -A && git commit -m "Initial import from disk" || true; git push || true; fi; fi && uvicorn src.watercooler_mcp.http_facade:app --host 0.0.0.0 --port "$PORT"
```

## GitHub OAuth App
- Homepage: `https://<worker>.<account>.workers.dev/`
- Callback: `https://<worker>.<account>.workers.dev/auth/callback`
- Scope: `read:user` (profile only)

## KV ACLs (default‑deny)
- Key: `user:gh:<login>` → JSON array of allowed projects, e.g. `["proj-jay"]`
- Seed via dashboard or CLI: `wrangler kv:key put --binding=KV_PROJECTS user:gh:<login> '["proj-jay"]'`

## Deploy
- Backend: set env + start command → Save/Deploy
- Worker staging: `npx wrangler deploy --env staging` (has `ALLOW_DEV_SESSION=true`)
- Worker production: `npx wrangler deploy --env production` (OAuth‑only)

## Staging Test Checklist
- OAuth: `/auth/login` → authorize → session cookie
- SSE (no dev session): `/sse?project=proj-jay` (Accept: `text/event-stream`)
- Tools: initialize → tools.list → health → say/read → commit in repo
- ACL: `proj-jay` 200; `proj-denied` 403
- Rate limit: 12× bad `/auth/callback` → 429 after 10/5m
- CSRF: bad/missing/reused state → 400/403
- Logs: `npx wrangler tail --env staging --format json | grep -E 'auth_|acl_|rate_limit'`

## Production Promotion
- Ensure `ALLOW_DEV_SESSION` is disabled in prod
- Verify `INTERNAL_AUTH_SECRET` matches (Worker ↔ Backend)
- Seed initial prod ACLs
- Deploy prod; repeat smoke tests (no dev session)

## Rollback SOP
- Roll back Worker: `npx wrangler deployments list --env production` → `npx wrangler rollback <ID> --env production`
- Use staging for diagnostics; keep dev session off in production
- Backend: revert env/start if needed; Git repo untouched

## Monitoring & Alerts
- Worker: `npx wrangler tail --env production --format json | grep -E 'auth_|acl_|rate_limit|error'`
- Backend: Render logs (/mcp/*), `/health` steady 200
- Suggested alerts: 5xx > 1%, ACL denials > 5/hour/user, rate limits > 10/min

## Security Guardrails (must)
- CSRF state (`/auth/login` → `/auth/callback`), cookie‑only sessions in prod
- Default‑deny ACL at Worker; 403 when user/project not allowlisted
- Backend fail‑fast if `INTERNAL_AUTH_SECRET` missing in production
- Structured logs for auth/session/ACL/rate‑limit events

## Common Troubleshooting
- 401: no session → visit `/auth/login`
- 406: missing `Accept: text/event-stream` on `/sse`
- 403: not in ACL → add project to `user:gh:<login>` allowlist
- 429: rate limit exceeded → wait window
- Git push fails: check Deploy Key write access on repo; see Render logs

## Links
- Full guide: `docs/DEPLOYMENT.md`
- Quickstart (clients): `docs/REMOTE_MCP_QUICKSTART.md`
- Helper scripts: `cloudflare-worker/scripts/`
