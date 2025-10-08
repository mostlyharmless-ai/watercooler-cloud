# Task Completion Checklist

When completing a task, ensure:

## 1. Testing
- [ ] Run pytest tests: `pytest tests/ -v`
- [ ] Verify all 56 tests pass
- [ ] Add new tests for new features
- [ ] Test specific modules if changes are isolated

## 2. Type Checking
- [ ] Run mypy: `mypy src/`
- [ ] Ensure no type errors

## 3. Code Quality
- [ ] Follow stdlib-only principle for core library
- [ ] Maintain Python 3.9+ compatibility
- [ ] Use structured entry format for watercooler threads
- [ ] Update documentation if API changes

## 4. Git Workflow
- [ ] Commit with descriptive messages
- [ ] Ensure .watercooler threads are properly formatted
- [ ] Verify merge driver config if collaborating

## 5. Documentation
- [ ] Update README.md if user-facing changes
- [ ] Update relevant docs in docs/ directory
- [ ] Update IMPLEMENTATION_PLAN.md or L5_MCP_PLAN.md if architectural

## 6. MCP Server
- [ ] Test MCP integration if server code changed
- [ ] Verify tools are properly exposed
- [ ] Update docs/mcp-server.md if tool changes
