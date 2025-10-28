# [ARCHIVED] Production Repo Sanitization & Deployment Playbook (Remote)

> Archived remote deployment guidance. Preferred path: local stdio MCP universal
> dev mode (docs/TESTER_SETUP.md).

Repo naming note
- Target production repo (final): `mostlyharmless-ai/watercooler-cloud`.
- Use this slug consistently in CI, docs, and deployment wiring.

Purpose
- Document, verify, and rehearse the complete “move to production” process for this codebase.
- Emphasize privacy/identity protection and general repo hygiene to make the repository public‑ready.
- Produce repeatable checklists and commands for operators.

Outcomes
- Clean, policy‑compliant production repository (names, history, assets, secrets).
- Fresh staging and production environments validated via acceptance tests.
- Clear rollback plan and operator runbook references.

Scope
- Repo hygiene (files, history, identity protection, secrets, assets) and CI/CD hardening.
- Cloud deployment (Render backend + Cloudflare Worker) with auth/ACL posture.
- Identity protection is optional and policy‑driven: techniques include mailmap author/committer normalization, message sanitization, and asset redaction.

Non‑Goals
- Feature work; changing business logic.
- Migrating GitHub issues/PRs.

---

## Phase A — Repository Sanitization (de‑crufting & identity protection)

Checklist
- [ ] Secrets: none in history or working tree
- [ ] Config drift removed; dev‑only scripts pruned
- [ ] Large/unused assets removed (and history pruned if needed)
- [ ] Identity protection applied as required by policy
- [ ] Licensing/headers checked; README/docs updated

1) Secret discovery (working tree)
```bash
rg -n "(?i)(api[_-]?key|secret|passwd|password|token|aws_|ghp_|github_pat)" -S --no-ignore --hidden \
  --glob '!**/.git/**' --glob '!**/node_modules/**' --glob '!**/.venv/**'
```
- Resolve findings (rotate keys; replace with env‑based config). Ensure `.gitignore` covers local secrets.

2) Secret/asset discovery (history)
- If history purge is required, use `git filter-repo`:
```bash
git clone --mirror <ssh-url> repo.git && cd repo.git
# Remove files by path pattern
git filter-repo --path-glob 'secrets/*.json' --invert-paths --force
# Or replace file contents matching pattern (advanced)
# git filter-repo --replace-text ../replacements.txt --force
```

3) Identity protection (optional; choose what policy requires)
- Metadata normalization (authors/committers) via mailmap:
```bash
# mailmap.txt pairs old → neutral identity
git filter-repo --force --mailmap ../mailmap.txt
```
- Content/message sanitization (advanced):
  - Replace text in commit messages or files using `--replace-text`
  - Redact/rotate embedded assets

4) Large file audit
```bash
git verify-pack -v .git/objects/pack/*.idx | sort -k3 -n | tail -20
```

5) Content sweep
```bash
rg -n "<old-name-or-brand>|TODO\(|FIXME|HACK" -S --no-ignore --hidden --glob '!**/.git/**'
```

---

## Phase B — CI/CD Hardening (GitHub Actions)

Goals
- Keep PR checks green while minimizing minutes.
- Default to Linux runners; gate macOS to releases/nightly.

Snippet
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

on:
  pull_request:
    paths-ignore:
      - '**/*.md'
      - 'docs/**'

jobs:
  test-linux:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps: [ ... caches + tests ... ]

  test-macos:
    if: startsWith(github.ref, 'refs/tags/') || github.event_name == 'schedule'
    runs-on: macos-latest
    steps: [ ... minimal matrix ... ]
```

---

## Phase C — Environment Provisioning (Staging → Production)

Policy
- Auth‑only posture: dev session disabled by default; tokens via `/console`.
- `AUTO_ENROLL_PROJECTS = "false"`; prefer explicit `create_project` + ACL seeding.

Staging (new stack)
1) Backend (Render)
- Env: `INTERNAL_AUTH_SECRET`, `BASE_THREADS_ROOT=/data/wc-cloud`, `WATERCOOLER_DIR=/data/wc-cloud`.
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
- Start: `uvicorn src.watercooler_mcp.http_facade:app --host 0.0.0.0 --port $PORT`.

2) Worker (Cloudflare)
- KV namespace: create/bind `KV_PROJECTS` for staging.
- Secrets (scoped): `./scripts/set-secrets.sh --env staging`.
- `wrangler.toml [env.staging.vars]`:
  - `BACKEND_URL = "https://<staging-backend>"`
  - `ALLOW_DEV_SESSION = "false"`
  - `AUTO_ENROLL_PROJECTS = "false"`
- Deploy: `./scripts/deploy.sh staging`.

3) ACL & Tokens
- Seed ACL: `./scripts/seed-acl.sh <github-login> <project>`.
- Issue token: `/console`.

Production
- Repeat with `[env.production]`; do not enable dev session.
- Use separate KV namespace if you need strict isolation.

---

## Phase D — Acceptance Tests (each env)

SSE attach (token)
```bash
npx -y mcp-remote \
  "https://<worker>.workers.dev/sse?project=<project>" \
  --header "Authorization: Bearer <TOKEN>"
# Expect: event: endpoint
```

JSON‑RPC via /messages (using the endpoint from SSE)
- `initialize` → `tools/list` → `watercooler_v1_health` → `watercooler_v1_say`.

Negative checks
- Forbidden project → 403 (ACL enforced).
- Token revoked → 401 on next call.

Logs
```bash
cd cloudflare-worker
npx wrangler tail --env <env> --format json | rg -n "session_validated|token_auth_success|do_dispatch_ok|acl_denied"
```

---

## Phase E — Cutover & Communication

- Announce timeline; freeze pushes during cutover.
- Re‑clone guidance:
```bash
git clone git@github.com:<org>/<repo>.git
# or retarget existing clone
git remote set-url origin git@github.com:<org>/<repo>.git
git fetch --all && git reset --hard origin/<default-branch>
```
- Update docs, badges, CI secrets, webhooks to production names.

---

## Phase F — Rollback

- Keep a private mirror backup before history operations.
- To revert a rewritten push:
```bash
git clone --mirror <backup-ssh> rollback.git
cd rollback.git && git push --force-with-lease --mirror git@github.com:<org>/<repo>.git
```

---

## Operator Checklists

Pre‑flight (each env)
- [ ] KV bound; secrets set (`set-secrets.sh --env <env>`)
- [ ] `INTERNAL_AUTH_SECRET` matches backend
- [ ] `ALLOW_DEV_SESSION` = false; `AUTO_ENROLL_PROJECTS` = false
- [ ] ACL seeded; test token issued

Acceptance (each env)
- [ ] SSE attaches; endpoint event received
- [ ] initialize → list → health → say stream over SSE
- [ ] Forbidden project → 403; revoked token → 401
- [ ] Logs show expected events

References
- OPERATOR_RUNBOOK.md, DEPLOYMENT.md, REMOTE_MCP_QUICKSTART.md
- cloudflare-worker/scripts/README.md
