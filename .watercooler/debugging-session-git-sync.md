# Watercooler-Cloud Git Sync Debugging Session

## Problem
Attempting to create threads on watercooler-cloud MCP service fails with "MCP error -32603: Internal error". Backend logs show:
- `GitSyncError: Failed to clone git@github.com:mostlyharmless-ai/watercooler-cloud-threads.git`
- `Load key "/data/secrets/wc_git_key": error in libcrypto`
- `Permission denied (publickey)`

## Root Causes Identified (from Codex review)

1. **SSH key format issue**: Using `printf '%b'` instead of `printf '%s'` causes escape interpretation
2. **Missing branch creation**: Empty repos fail because no branch is created before first commit
3. **Non-git directory handling**: Cloning into existing non-empty non-git directory fails
4. **Path mismatch**: Production service logs show `/data/wc-staging` instead of `/data/wc-production`

## Fixes Applied

### PRs Merged
- **PR #1**: Added `create_if_missing` parameter to SayRequest model (merged to main)
  - Files: `src/watercooler_mcp/http_facade.py:75`, `src/watercooler_mcp/server.py:360`
- **PR #2**: Added cleanup logic for non-git directories in git sync (merged to main)
  - File: `src/watercooler_mcp/git_sync.py:117-120`

### Hardened Start Commands (Ready but NOT YET APPLIED)

**Location**:
- `/tmp/production_start_command.sh` - for watercooler-cloud (srv-d3ua812li9vc73bup5c0)
- `/tmp/staging_start_command.sh` - for watercooler-cloud-staging (srv-d3ua7bali9vc73buoiug)

**Key improvements in hardened commands**:
1. `printf '%s'` instead of `printf '%b'` - prevents SSH key corruption
2. Backup/restore flow: `mv /data/wc-production /data/wc-production.bak.$ts` before clone
3. Branch creation: `git switch -c "${WATERCOOLER_GIT_BRANCH:-main}"` for empty repos
4. Uses env var defaults: `${WATERCOOLER_GIT_AUTHOR:-Watercooler Bot}`
5. Import logic: copies back from backup and commits if data existed

## Current Status

**Production Service (srv-d3ua812li9vc73bup5c0)**:
- Status: Live but failing on git operations
- Issue: Still using OLD start command (has `printf '%b'` and wrong path `/data/wc-staging`)
- Action needed: Update start command from `/tmp/production_start_command.sh` in Render dashboard

**Staging Service (srv-d3ua7bali9vc73buoiug)**:
- Status: Unknown, likely has similar issues
- Action needed: Update start command from `/tmp/staging_start_command.sh` in Render dashboard

## Next Steps

1. **Manual update required**: Copy start commands from scratch files into Render dashboard
2. **Trigger deployment**: After updating, manually deploy both services
3. **Test thread creation**: Use `mcp__watercooler-cloud__watercooler_v1_say` with `create_if_missing=true`
4. **Verify git sync**: Check logs to ensure clone succeeds and SSH key loads properly

## Test Thread Details

**Topic**: `thread-migration-strategy`
**Title**: Discussion: Migrating Threads to New Watercooler-Cloud Service
**Body**: Migration strategy discussion for moving local .watercooler threads to cloud service

## Environment Variables to Verify

After updating start commands, verify these are set:
- `WATERCOOLER_GIT_REPO` - git@github.com:mostlyharmless-ai/watercooler-cloud-threads.git
- `GIT_SSH_PRIVATE_KEY` - Deploy key with write access to threads repo
- `WATERCOOLER_DIR` and `BASE_THREADS_ROOT` - should match (set in start command)
- `INTERNAL_AUTH_SECRET` - matches Cloudflare Worker config

## Key Files Modified

- `.gitignore` - Added `.env.production`, `.env.staging`, `.secrets/`
- `src/watercooler_mcp/http_facade.py` - Added `create_if_missing` parameter
- `src/watercooler_mcp/server.py` - Added `create_if_missing` parameter
- `src/watercooler_mcp/git_sync.py` - Added non-git directory cleanup logic

## Reference Documentation

See also:
- `docs/DUAL_STACK_DEPLOYMENT.md:253` - Hardened start command example
- `docs/OPERATOR_RUNBOOK.md:19` - Operational guidance
- Codex review notes emphasize: printf '%s', branch creation, backup flow
