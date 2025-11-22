# Fixing sync_branch_state Merge Operation Bug

## Context
Working on watercooler-cloud MCP server. User tried to merge post-launch-polish branch to main in threads repo using `watercooler_v1_sync_branch_state` tool, but merge wasn't being pushed to remote.

## Bug Found
File: `src/watercooler_mcp/server.py`, line 1909-1914

The merge operation in `sync_branch_state()` performs a local git merge but never pushes to the remote:
```python
threads_repo.git.checkout("main")
try:
    threads_repo.git.merge(target_branch, '--no-ff', '-m', f"Merge {target_branch} into main")
    result_msg = f"✅ Merged '{target_branch}' into 'main' in threads repo."
    if warnings:
        result_msg += "\n" + "\n".join(warnings)
```

## User's Requirement
"We want to maintain sync between the paired code and threads repos locally and remotely. The push should happen on threads if it has happened on code, but not if it has not."

## Fix Implemented
Modified `src/watercooler_mcp/server.py` lines 1911-1932 to:
1. Check if the code repo branch exists on remote
2. If code branch is on remote, push the threads merge too
3. If code branch is local-only, keep threads merge local-only

New code:
```python
threads_repo.git.checkout("main")
try:
    threads_repo.git.merge(target_branch, '--no-ff', '-m', f"Merge {target_branch} into main")

    # Check if code repo branch exists on remote - if yes, push threads merge too
    code_branch_on_remote = False
    if context.code_root:
        try:
            code_repo_obj = Repo(context.code_root, search_parent_directories=True)
            remote_refs = [ref.name for ref in code_repo_obj.remote().refs]
            code_branch_on_remote = f"origin/{target_branch}" in remote_refs
        except Exception:
            pass  # Ignore errors checking remote

    if code_branch_on_remote:
        # Code branch is on remote, push threads merge too
        threads_repo.git.push('origin', 'main')
        result_msg = f"✅ Merged '{target_branch}' into 'main' in threads repo and pushed to remote."
    else:
        # Code branch is local only, keep threads merge local
        result_msg = f"✅ Merged '{target_branch}' into 'main' in threads repo (local only - code branch not on remote)."

    if warnings:
        result_msg += "\n" + "\n".join(warnings)
```

## Current Issue
After restarting MCP server (`/mcp` command), the fix isn't being picked up. The tool still returns old message format:
- Old: "✅ Merged 'post-launch-polish' into 'main' in threads repo."
- Expected: "✅ Merged 'post-launch-polish' into 'main' in threads repo and pushed to remote."

The code change is saved in the file (verified with grep), but MCP server is running old code.

## Next Steps
1. Check where MCP server is installed (package vs editable install)
2. Reinstall if needed: `pip install -e .` from watercooler-cloud root
3. Restart MCP server again
4. Test with: `sync_branch_state(code_path=".", branch="post-launch-polish", operation="merge", force=true)`

## Test Scenario
- Code repo: post-launch-polish branch exists on origin/post-launch-polish
- Threads repo: post-launch-polish has 88 commits ahead of main
- Expected: Merge and push to remote (since code branch is on remote)
- Currently: Tool reports success but no actual merge happens

## Files Modified
- `/media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-cloud/src/watercooler_mcp/server.py` (lines 1911-1932)