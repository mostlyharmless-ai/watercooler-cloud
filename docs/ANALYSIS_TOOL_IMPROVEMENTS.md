# Tool Usage Analysis: `watercooler_v1_sync_branch_state` Parameter Error

## Failure Sequence

1. **Initial Attempt**: User requested posting entries to `linear-integration` thread
   - **Action**: Called `watercooler_v1_say` with `agent_func` parameter
   - **Result**: ✅ Correct usage, but blocked by branch pairing validation (expected behavior)
   - **Error Message**: Clear and actionable: "Run: watercooler_v1_sync_branch_state with operation='checkout' to sync branches"

2. **First Sync Attempt**: Attempted to sync branches
   - **Action**: Called `watercooler_v1_sync_branch_state` with `agent_func="Cursor:Auto:planner"` parameter
   - **Result**: ❌ Pydantic validation error: "Unexpected keyword argument [type=unexpected_keyword_argument, input_value='Cursor:Auto:planner', input_type=str]"
   - **Root Cause**: Function does NOT accept `agent_func` parameter, but model assumed it would (pattern matching from other tools)

3. **Second Sync Attempt**: Retried without `agent_func`
   - **Action**: Called `watercooler_v1_sync_branch_state` with only valid parameters
   - **Result**: ✅ Success - branches synced correctly

## Model Reasoning Error

The model incorrectly assumed `sync_branch_state` would accept `agent_func` because:
- **Pattern Recognition**: Other write operations (`say`, `ack`, `handoff`, `set_status`) all accept `agent_func`
- **Incomplete Function Signature Review**: Model saw the function name and operation but didn't fully verify parameter list
- **Missing Explicit Exclusion**: Function docstring doesn't explicitly state what parameters are NOT accepted

## Function Documentation Issues

### Current Documentation (lines 1353-1369)

```python
"""Synchronize branch state between code and threads repos.

Performs branch lifecycle operations to keep repos in sync:
- create: Create threads branch if code branch exists
- delete: Delete threads branch if code branch deleted (with safeguards)
- merge: Merge threads branch to main if code branch merged
- checkout: Ensure both repos on same branch

Args:
    code_path: Path to code repository directory
    branch: Specific branch to sync (default: current branch)
    operation: One of "create", "delete", "merge", "checkout"
    force: Skip safety checks (use with caution)

Returns:
    Operation result with success/failure and any warnings.
"""
```

### Issues Identified

1. **Missing Parameter Clarity**: Doesn't explicitly state that `agent_func` is NOT accepted
2. **No Rationale**: Doesn't explain WHY `agent_func` isn't needed (this is an operational tool, not a write operation requiring provenance)
3. **No Comparison**: Doesn't distinguish this tool from write operations that DO require `agent_func`
4. **Incomplete Parameter List**: Doesn't mention `ctx` parameter (though this is FastMCP convention)

## Error Message Issues

### Current Error Message

```
1 validation error for call[sync_branch_state]
agent_func
  Unexpected keyword argument [type=unexpected_keyword_argument, input_value='Cursor:Auto:planner', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/unexpected_keyword_argument
```

### Issues

1. **Not User-Friendly**: Technical Pydantic error, not actionable guidance
2. **No Valid Parameter List**: Doesn't show what parameters ARE accepted
3. **No Context**: Doesn't explain why this parameter isn't valid
4. **No Suggestion**: Doesn't suggest removing the parameter or checking documentation

## Recommended Improvements

### 1. Enhanced Function Docstring

```python
"""Synchronize branch state between code and threads repos.

Performs branch lifecycle operations to keep repos in sync:
- create: Create threads branch if code branch exists
- delete: Delete threads branch if code branch deleted (with safeguards)
- merge: Merge threads branch to main if code branch merged
- checkout: Ensure both repos on same branch

**Note**: This is an operational tool that does NOT require `agent_func`.
Unlike write operations (say, ack, handoff, set_status), this tool performs
git operations that don't create thread entries, so no agent provenance is needed.

Args:
    code_path: Path to code repository directory (default: current directory)
    branch: Specific branch to sync (default: current branch)
    operation: One of "create", "delete", "merge", "checkout" (default: "checkout")
    force: Skip safety checks (use with caution, default: False)

Returns:
    Operation result with success/failure and any warnings.

Example:
    sync_branch_state(code_path=".", branch="feature-auth", operation="checkout")
"""
```

### 2. Improved Error Handling

FastMCP automatically rejects unexpected parameters with Pydantic validation.
While custom **kwargs-based validation would be ideal for providing context-specific
error messages, FastMCP doesn't support **kwargs in tool functions.

Instead, we rely on FastMCP's built-in validation and clarify in the docstring
that agent_func is not needed:

### 3. Tool Parameter Documentation Consistency

Create a pattern for documenting parameter requirements:

- **Write Operations** (say, ack, handoff, set_status): Require `agent_func` for provenance
- **Read Operations** (list_threads, read_thread): Don't require `agent_func`
- **Operational Tools** (sync_branch_state, validate_branch_pairing): Don't require `agent_func`

Add this pattern to the module docstring or a shared documentation section.

### 4. FastMCP Tool Schema Enhancement

Consider if FastMCP allows custom parameter validation that could:
- Reject unknown parameters with a helpful message
- Show valid parameters in error response
- Link to documentation

## Implementation Status

1. **✅ Completed**: Add explicit note in docstring about `agent_func` not being needed
   - Updated `src/watercooler_mcp/server.py:1361-1366`
   - Updated `docs/mcp-server.md:327-332`

2. **❌ Not Feasible**: Add `**kwargs` catch with helpful error message
   - Investigation Result: FastMCP doesn't support `**kwargs` in tool functions
   - Error: `ValueError: Functions with **kwargs are not supported as tools`
   - Resolution: Rely on FastMCP's built-in Pydantic validation for parameter checking
   - FastMCP automatically rejects unexpected parameters with clear error messages

3. **✅ Completed**: Create parameter pattern documentation
   - Updated docstring to clarify operational vs write operation parameter requirements

4. **Future**: Explore FastMCP schema enhancements
   - Could investigate if FastMCP allows custom error message formatting for validation errors
   - Not critical since current Pydantic errors are clear and actionable

## Testing Recommendations

**Status**: FastMCP's parameter validation prevents invalid parameters at the framework level:
- ✅ FastMCP automatically rejects unexpected parameters (Pydantic validation)
- ✅ Error messages identify the unexpected parameter by name
- ⚠️ Error messages are generic ("unexpected keyword argument") rather than domain-specific
- 📝 Domain-specific guidance provided through enhanced docstrings instead

The trade-off is acceptable: clear docstrings prevent misuse, and FastMCP's validation provides a safety net with adequate error messages.

