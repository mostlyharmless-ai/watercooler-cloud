---
Entry: Codex (caleb) 2025-10-25T00:00:00Z
Type: Note
Title: Cloudflare Worker OAuth — client_id=undefined (Root Cause & Fix)

Summary
- Symptom: OAuth redirect URL contained `client_id=undefined`, leading to GitHub 404 / login failure.
- Scope: Cloudflare Worker (staging/prod). Secrets are environment‑scoped in Wrangler.

Root Cause
- Required secrets were not configured for the active environment. Only the default scope had values, so in staging/prod `env.GITHUB_CLIENT_ID` and `env.GITHUB_CLIENT_SECRET` were undefined.

Fix (Per Environment)
```bash
cd cloudflare-worker

# Recommended helper (interactive)
./scripts/set-secrets.sh --env staging     # or --env production

# Manual alternative
echo "<GITHUB_CLIENT_ID>"     | npx wrangler secret put GITHUB_CLIENT_ID --env staging
echo "<GITHUB_CLIENT_SECRET>" | npx wrangler secret put GITHUB_CLIENT_SECRET --env staging
echo "<INTERNAL_AUTH_SECRET>" | npx wrangler secret put INTERNAL_AUTH_SECRET --env staging
```

Verification
```bash
# 1) List env‑scoped secrets
npx wrangler secret list --env staging    # expect: GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, INTERNAL_AUTH_SECRET

# 2) Probe Worker debug endpoint (presence/lengths only)
curl -sS https://<your-worker-domain>/debug/secrets | jq
# → { has_github_client_id: true, github_client_id_length: 20, ... }
```

Notes
- `INTERNAL_AUTH_SECRET` must match exactly on the Backend (Render env var) and the Worker.
- This was validated and captured in `.watercooler/watercooler-cloud-ux.md` under “Staging Deployment — Secrets Issue & Resolution”.
- DEPLOYMENT guide updated with a troubleshooting entry and a “secrets preflight” reminder.

Status
- Documented; add “wrangler secret list --env <env>” to every pre‑deploy checklist.

