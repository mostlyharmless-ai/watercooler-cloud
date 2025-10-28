# New Repo Creation + Sanitized Migration (Option B) — Zero‑to‑Deployed Dry Run

Repo naming note
- NEW_REPO for this plan is fixed to: `mostlyharmless-ai/watercooler-cloud`.
- Treat this as final for all commands, docs, and deployment wiring.

Intent
- Create a brand‑new production repository with sanitized history/metadata (identity protection and content hygiene as needed), with strict disassociation from the old repo.
- Exercise and validate the full deployment pathway with fresh instances (staging → production) to verify documentation and operational understanding end‑to‑end.
- Outcome: New repo live; deployments point to new repo; old repo decommissioned/removed. No GitHub redirect path from new → old.

Scope & Non‑Goals
- Preserves: Code, tags/branches (rewritten SHAs). Does not migrate issues or PRs (kept in old repo archive/export if needed).
- Disassociates: Repo name and author/committer metadata. Does not remove third‑party caches or forks.
- Optional: Commit message rewrites (e.g., Co‑authored‑by trailers) — not required for author anonymization and more invasive.

Definitions
- `OLD_REPO`: mostlyharmless-ai/watercooler-collab
- `NEW_REPO`: mostlyharmless-ai/watercooler-cloud
- Identity protection: optional techniques to remove or normalize personal identifiers in Git history and/or content (e.g., mailmap author/committer rewrite, message sanitization, asset redaction).

Prerequisites
- Org admin privileges on GitHub.
- Local: Git ≥ 2.30, `git-filter-repo` installed (brew or pipx).
- Access to Render and Cloudflare accounts (Worker + KV) used by Watercooler.

High‑Level Plan
1) Inventory identities and rewrite history locally (no remote changes yet).
2) Create NEW repo on GitHub; push rewritten mirror there (no redirects from OLD).
3) Provision brand‑new staging environment (backend + Worker) wired to NEW repo.
4) Acceptance tests on staging (OAuth/tokens, SSE, tools, ACLs).
5) Provision production for NEW repo; repeat acceptance.
6) Decommission OLD repo (archive → delete); break any stale paths.
7) Communicate, cut over, and monitor.

Detailed Playbook

Phase 0 — Discovery & Planning
- Enumerate all author/committer variants used by the collaborator:
  ```bash
  git clone --mirror git@github.com:mostlyharmless-ai/watercooler-collab.git wc-old.git
  cd wc-old.git
  git log --all --format='%aN <%aE>' | sort -u > ../authors.txt
  git log --all --format='%cN <%cE>' | sort -u > ../committers.txt
  ```
- Build a list of every email/name alias for the collaborator from those files.

Phase 1 — Local Rewrite & Sanitization (no remote)
1. Prepare mailmap with a neutral identity (add all aliases):
   ```bash
   cat > ../mailmap.txt << 'EOF'
   Removed Contributor <removed@example.com> Former Name <old1@example.com>
   Removed Contributor <removed@example.com> Former Alias <old2@example.org>
   Removed Contributor <removed@example.com> <old3@example.net>
   # add every known email/name variant, one per line
   EOF
   ```
   Example above shows author/committer metadata rewrite. Choose only those identity protection steps you require.
2. Rewrite in a fresh mirror and verify:
   ```bash
   cd ..
   rm -rf wc-old.git && git clone --mirror git@github.com:mostlyharmless-ai/watercooler-collab.git wc-old.git
   cd wc-old.git
   git filter-repo --force --mailmap ../mailmap.txt

   # Verification: no old authors remain
   git log --all --author='Former Name' | wc -l        # → 0
   git log --all --format='%aN <%aE>' | rg 'old@|Former' || true
   ```
3. Optional (content identity sweep): scan and update references in repo content (not part of filter‑repo):
   ```bash
   # Inspect for mentions of old names/emails or repo name
   rg -n "old1@example.com|Former Name|watercooler-collab" -S --no-ignore --hidden --glob '!**/.git/**'
   # Edit as needed; these edits produce new HEAD commits after push
   ```
4. Optional (commit message sanitization): rewriting `Co-authored-by:` lines or other message text requires a message‑rewrite callback; use only if policy requires it.

Phase 2 — Establish NEW repo and push rewritten history
1. Create NEW repo (GitHub UI or gh):
   ```bash
   gh repo create mostlyharmless-ai/watercooler-cloud --private --confirm
   ```
2. Push the rewritten mirror to NEW:
   ```bash
   cd wc-old.git
   git remote set-url origin git@github.com:mostlyharmless-ai/watercooler-cloud.git
   git push --mirror origin
   git tag -a history-rewrite-$(date +%Y%m%d) -m "History rewrite (author anonymization)"
   git push --tags
   ```
3. Protect the default branch, re‑enable Actions, and set required checks on NEW.

Phase 3 — Provision fresh STAGING from NEW
Backend (Render)
- Create a new Web Service bound to NEW repo.
- Disk: attach `/data` and set `BASE_THREADS_ROOT=/data/wc-cloud`, `WATERCOOLER_DIR=/data/wc-cloud`.
- Secrets: set `INTERNAL_AUTH_SECRET` (match Worker), and any git sync secrets if used.
- **CRITICAL:** If using git sync (`WATERCOOLER_GIT_REPO`), initialize the threads repository first:
  ```bash
  # Create empty repo on GitHub, add deploy key with write access, then:
  cd /tmp
  git clone git@github.com:<org>/watercooler-cloud-threads[-staging].git
  cd watercooler-cloud-threads[-staging]
  git commit --allow-empty -m "Initialize threads repo"
  git push -u origin main
  ```
  Without this, the Render service will fail to clone (repo has no refs/branches).
- Start: `uvicorn src.watercooler_mcp.http_facade:app --host 0.0.0.0 --port $PORT`

Worker (Cloudflare)
- Use repo’s `cloudflare-worker/` directory; adopt a distinct Worker name for the NEW stack.
- KV: create a NEW KV namespace for staging (to keep ACL/tokens isolated from the old stack).
  ```bash
  cd cloudflare-worker
  npx wrangler kv:namespace create "KV_PROJECTS"
  # add new id to wrangler.toml [env.staging]
  ```
- Secrets (environment‑scoped):
  ```bash
  ./scripts/set-secrets.sh --env staging   # sets GITHUB_CLIENT_ID/SECRET, INTERNAL_AUTH_SECRET
  ```
- Config posture: `[env.staging.vars]`
  - `ALLOW_DEV_SESSION = "false"`
  - `AUTO_ENROLL_PROJECTS = "false"`
  - `BACKEND_URL = "https://<staging-backend.onrender.com>"`
- Deploy staging:
  ```bash
  ./scripts/deploy.sh staging
  ```

ACL & Tokens (staging)
- Seed ACL for your user: `./scripts/seed-acl.sh <github-login> <project>`
- Issue a token: `https://<staging-worker>.workers.dev/console`

Acceptance (staging)
- Open SSE with token:
  ```bash
  npx -y mcp-remote \
    "https://<staging-worker>.workers.dev/sse?project=<project>" \
    --header "Authorization: Bearer <TOKEN>"
  # Expect: event: endpoint
  ```
- In a second terminal: POST JSON‑RPC to `/messages` (using `endpoint`) for `initialize` → `tools/list` → `watercooler_v1_health` → `watercooler_v1_say`.
- Negative checks: forbidden project → 403; revoke token → next call 401.
- Logs: `npx wrangler tail --env staging --format json` → see `session_validated`, `token_auth_success`, `do_dispatch_ok`.

Phase 4 — Provision PRODUCTION for NEW
- Repeat backend + Worker setup under `[env.production]` with a distinct KV namespace and production URLs.
- Do NOT set `ALLOW_DEV_SESSION` in production; keep `AUTO_ENROLL_PROJECTS = "false"`.
- Seed minimal ACL; perform production acceptance (token, SSE, health/list/say, deny/revoke tests).

Phase 5 — Communication & Cutover
- Announce timeline, motivation, and actions users must take (new clone URL, tokens, ACLs).
- Provide re‑clone instructions:
  ```bash
  git clone git@github.com:mostlyharmless-ai/watercooler-cloud.git
  # or retarget existing clone (will diverge SHAs):
  git remote set-url origin git@github.com:mostlyharmless-ai/watercooler-cloud.git
  git fetch --all && git reset --hard origin/<default-branch>
  ```
- Update docs/badges/links to NEW repo name; update CI, webhooks, and deployment hooks to NEW paths.

Phase 6 — Decommission OLD
- Archive OLD for a quarantine period (read‑only), then delete.
- If you ever renamed the old name earlier (not in this plan), create a private placeholder with the old name to break redirects. In this Option B flow (no rename), there are no redirects.
- Remove any deployment services still pointing at OLD.

Phase 7 — Rollback
- Keep a private mirror backup of OLD (pre‑rewrite). To revert NEW to pre‑rewrite history:
  ```bash
  git clone --mirror git@github.com:mostlyharmless-ai/<BACKUP_REPO>.git rollback.git
  cd rollback.git && git push --force-with-lease --mirror git@github.com:mostlyharmless-ai/watercooler-cloud.git
  ```

Operational Checklists

Pre‑flight (each env)
- [ ] KV namespace exists and bound.
- [ ] Secrets set via `set-secrets.sh --env <env>`.
- [ ] `INTERNAL_AUTH_SECRET` matches between Worker and backend.
- [ ] `BACKEND_URL` points to the correct backend.
- [ ] `ALLOW_DEV_SESSION` disabled; `AUTO_ENROLL_PROJECTS` disabled.
- [ ] ACL seeded; tokens issued via `/console`.

Acceptance (each env)
- [ ] SSE opens with Bearer token; endpoint event received.
- [ ] initialize → tools/list → health → say stream over SSE.
- [ ] Forbidden project returns 403; revocation returns 401.
- [ ] Logs show `session_validated`, `token_auth_success`, `do_dispatch_ok`.

Risk Notes
- All SHAs change (mirror rewrite). Contributors must re‑clone or hard‑reset.
- Issues/PRs are not migrated (Option B); preserve snapshots separately if needed.
- Commit message content is not rewritten (only author/committer metadata); avoid changing messages unless strictly required.

References
- DEPLOYMENT.md (staging/prod posture, token mode)
- OPERATOR_RUNBOOK.md
- cloudflare-worker/scripts/README.md
