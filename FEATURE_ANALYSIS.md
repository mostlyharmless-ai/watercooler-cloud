# Feature Analysis: Removed Capabilities from acpmonkey

**Date:** 2025-10-06
**Concern:** watercooler-collab has removed significant structure that was intentionally designed in acpmonkey
**Status:** ⚠️ CRITICAL - Major features removed without justification

---

## Executive Summary

The watercooler-collab library has **removed critical structured collaboration features** that were intentionally designed into acpmonkey's watercooler system. These weren't optional bells and whistles — they were core to the collaboration protocol.

**Impact:** The simplified library cannot properly support the agentic collaboration workflow that acpmonkey depends on.

---

## 1. Entry Structure (REMOVED)

### What acpmonkey Has:
```markdown
---
Entry: Claude (jay) 2025-10-06T17:32:52Z
Type: Plan
Title: Proposal: Extract Watercooler into Standalone Library

[Body content here]
```

### What watercooler-collab Produces:
```markdown
---

- Updated: 2025-10-06T17:32:52Z by jay

[Body content here]
```

### Why This Matters:

**1. Entry Type Classification**
- **Types:** Note, Plan, Decision, PR, Closure
- **Purpose:** Enables filtering, searching, and understanding entry intent at a glance
- **Use case:** "Show me all Decisions in this thread" or "What Plans are pending?"
- **Lost capability:** No way to distinguish a casual note from a binding decision

**2. Entry Titles**
- **Purpose:** Scannable thread history without reading full bodies
- **Use case:** Quick review of "what happened in this thread?"
- **Example from real thread:**
  - "Proposal: Extract Watercooler into Standalone Library"
  - "Phase 1 ACK & Next Actions"
  - "Critical Findings & Risks"
- **Lost capability:** Thread becomes wall of text with no structure

**3. Agent Attribution**
- **Format:** `Entry: Claude (jay)` or `Entry: Codex` or `Entry: Team (caleb)`
- **Purpose:** Clear attribution with role (Claude=planner, Codex=implementer, Team=human)
- **Use case:** "Who made this decision?" or "Filter to Codex's entries"
- **Lost capability:** Only shows username, loses agent role context

---

## 2. Role System (REMOVED)

### What acpmonkey Has:
```python
--role planner     # Strategic planning, architecture
--role critic      # Code review, quality assurance
--role implementer # Writing code, tests
--role tester      # Test design, validation
--role pm          # Project management, coordination
--role scribe      # Documentation, recording
```

### What watercooler-collab Has:
Nothing. Removed entirely.

### Why This Matters:

**1. Multi-Agent Workflows**
- Real scenario: Claude acts as both planner AND reviewer
- Entry header shows which role: `Claude (jay) as critic` vs `Claude (jay) as planner`
- Critical for understanding context of comments

**2. Human Team Member Roles**
- Team members wear different hats: "Team (caleb) as pm" vs "Team (sarah) as tester"
- Provides accountability and context
- Tracks who contributed what expertise

**3. Workflow Tracking**
- Protocol: Plan → Implement → Review → Test → Document
- Role tracking ensures all steps happen
- Missing: No way to verify "did someone review this?"

---

## 3. Templates (PARTIALLY REMOVED)

### What acpmonkey Has:
```markdown
# Template: _TEMPLATE_entry_block.md
---
Entry: {{AGENT}} {{UTC}}
Type: {{TYPE}}
Title: {{TITLE}}

{{BODY}}
```

### What watercooler-collab Has:
We bundled the templates but **don't use them**. Commands generate minimal entries instead.

### Why This Matters:

**1. Consistency**
- All entries follow same format
- Easy to parse programmatically
- Tools can extract structured data

**2. Customization**
- Projects can override templates
- Add project-specific fields
- Maintain consistent branding

**3. Currently Broken**
- We ship templates but ignore them
- Commands hard-code their own format
- Templates are dead code

---

## 4. Template Discovery (REMOVED)

### What acpmonkey Has:
```python
def get_templates_dir(arg_dir: str | None) -> Path:
    # 1. Check explicit argument
    # 2. Check WATERCOOLER_TEMPLATES env var
    # 3. Check project-local templates (./watercooler/)
    # 4. Fall back to package defaults
```

### What watercooler-collab Has:
No template loading at all. No `--templates-dir` flag. No override mechanism.

### Why This Matters:

**1. Project Customization**
- Different projects need different entry formats
- Example: Research project might add "Experiment ID" field
- Example: Product team might add "Jira Ticket" field

**2. Team Consistency**
- Team defines templates in their repo
- All agents/humans use same format
- No central configuration needed

**3. Migration Path**
- acpmonkey users can't bring their custom templates
- Forces format change during migration
- Breaks existing workflows

---

## 5. Agent Registry (REMOVED)

### What acpmonkey Has:
```python
--agents-file agents.json

# agents.json
{
  "aliases": {
    "bot": "codex",
    "ai": "claude",
    "human": "team"
  },
  "counterparts": {
    "codex": "claude",
    "claude": "team",
    "team": "codex"
  },
  "default": "codex"
}
```

### What watercooler-collab Has:
Hard-coded: `{"codex": "claude", "claude": "codex"}`

### Why This Matters:

**1. Custom Agent Names**
- Not everyone uses "Codex" and "Claude"
- Example: "GPT4", "Gemini", "Human"
- No way to customize

**2. Multi-Agent Systems**
- More than 2 agents in conversation
- Example: Planner → Implementer → Reviewer → QA
- Hard-coded 2-agent flip breaks this

**3. Team Workflows**
- acpmonkey has Team as third agent
- Ball can be: Codex → Claude → Team → Codex
- Our library only flips between two agents

**4. Agent Tagging**
- acpmonkey supports: `claude#experiment-1` vs `claude#production`
- Different instances of same agent
- Removed completely

---

## 6. Structured Arguments (REMOVED)

### What acpmonkey Has:
```bash
# say command
watercooler say topic \
  --title "Quick update on Phase 2" \
  --type Note \
  --body-file message.txt \
  --agent codex \
  --role implementer \
  --status "IN_REVIEW" \
  --ball claude

# append-entry command (full structure)
watercooler append-entry topic \
  --agent codex \
  --role implementer \
  --title "Completed pagination fix" \
  --type PR \
  --body-file summary.txt \
  --status "IN_REVIEW" \
  --ball claude
```

### What watercooler-collab Has:
```bash
# say command (simplified)
watercooler say topic --body "message" --author jay

# append-entry command (simplified)
watercooler append-entry topic --body "message" --author jay
```

### Why This Matters:

**Lost Capabilities:**
1. Can't set entry type (is it a note or decision?)
2. Can't set entry title (requires reading full body)
3. Can't specify agent role (what capacity are they acting in?)
4. Can't set status in same command (requires separate call)
5. Can't control ball flip (auto-flips or doesn't)

**Workflow Impact:**
- acpmonkey: One command does everything
- watercooler-collab: Multiple commands to achieve same result
- More chance for inconsistency

---

## 7. Real-World Usage Example

### Scenario: Code Review Complete

**acpmonkey (1 command):**
```bash
watercooler say pr12_review \
  --agent claude \
  --role critic \
  --title "Code Review Complete - Approval with Minor Notes" \
  --type Decision \
  --body-file review.md \
  --status "IN_REVIEW" \
  --ball codex
```

**Result:**
```markdown
---
Entry: Claude (jay) 2025-10-06T18:00:00Z
Type: Decision
Title: Code Review Complete - Approval with Minor Notes

[Review content]
```
- Thread marked IN_REVIEW
- Ball passes to Codex
- Entry clearly shows this is a Decision by Claude acting as critic
- Title visible in thread scan

**watercooler-collab (3+ commands):**
```bash
# 1. Add entry (no type, no title, no role)
watercooler say pr12_review --author jay --body @review.md

# 2. Set status separately
watercooler set-status pr12_review in_review

# 3. Set ball separately
watercooler set-ball pr12_review codex
```

**Result:**
```markdown
---

- Updated: 2025-10-06T18:00:00Z by jay

[Review content]
```
- Multiple commands for one action
- Lost: Entry type (Decision)
- Lost: Entry title
- Lost: Agent role (critic)
- Lost: Atomicity (ball could flip before status updates)

---

## 8. Index and NEW Marker Impact

### What acpmonkey Shows:
```markdown
## Actionable (Ball: Codex)
- pr12_review.md — NEW — Decision by Claude — "Code Review Complete" — 2025-10-06
```

Key info at a glance:
- NEW marker (needs attention)
- Entry type (Decision)
- Who posted (Claude)
- What about (Code Review Complete)

### What watercooler-collab Shows:
```markdown
## Actionable (Ball: codex)
- pr12_review.md — NEW — 2025-10-06
```

Lost info:
- No entry type
- No title
- Generic attribution

---

## 9. Breaking Changes for acpmonkey Migration

If acpmonkey tries to use watercooler-collab as a library:

### ❌ **Breaking: Entry Format**
- Existing threads have structured entries
- New entries would be unstructured
- Mixed format in same thread (confusing)

### ❌ **Breaking: Templates**
- acpmonkey has custom templates
- Library ignores them completely
- Consistency breaks

### ❌ **Breaking: Agent Registry**
- acpmonkey defines 3 agents: Codex, Claude, Team
- Library only knows 2: codex ↔ claude
- Team agent doesn't work

### ❌ **Breaking: CLI Arguments**
- All shell scripts break
- Roles don't exist
- Types don't exist
- Titles don't exist

### ❌ **Breaking: Index Format**
- Library shows minimal info
- acpmonkey shows rich info
- Index becomes less useful

---

## 10. What Was The Original Plan?

Looking at `IMPLEMENTATION_PLAN.md`:

> "The goal is to create a reusable, stdlib-only Python package that maintains **100% CLI parity** with the current watercooler.py implementation."

We **explicitly planned** for full parity, then removed features without discussion.

The plan called for:
- ✅ Extract all functions (we did this)
- ✅ Maintain CLI structure (we did this)
- ❌ **Preserve all arguments** (we removed most)
- ❌ **Bundle templates** (we bundled but don't use)
- ❌ **Support agent registry** (we removed this)
- ❌ **Template discovery** (we removed this)

---

## 11. Why Did This Happen?

Looking at git history:

1. **Initial extraction** (commit 7102608) already simplified
2. **No intermediate review** of removed features
3. **Tests only cover simplified API** (so they pass)
4. **Documentation reflected simplified version** (so it seemed complete)

The simplification was **not a conscious decision** — it happened during extraction and wasn't noticed until now.

---

## 12. Options Going Forward

### Option A: Restore Full Features (Recommended)
**Goal:** Achieve 100% CLI parity as originally planned

**Add back:**
1. Entry structure (Type, Title, Agent)
2. Role system (6 roles)
3. Template loading and discovery
4. Agent registry support
5. Structured CLI arguments
6. Rich index generation

**Effort:** Moderate (2-3 days)
**Risk:** Low (we have reference implementation)
**Benefit:** True library that acpmonkey can adopt

### Option B: Document As "Simplified Alternative"
**Goal:** Accept this as a different design

**Changes:**
1. Update all docs: "This is NOT a replacement for acpmonkey"
2. Rename to make clear: `watercooler-simple` or `watercooler-lite`
3. Document use cases: "Good for simple note-taking, not structured collaboration"
4. Warning: "acpmonkey cannot migrate to this library"

**Effort:** Low (documentation only)
**Risk:** High (wasted the extraction effort)
**Benefit:** Quick resolution, but library has limited use

### Option C: Hybrid Approach
**Goal:** Support both simple and structured modes

**Design:**
1. Simple commands work as-is (current state)
2. Add `--structured` flag to enable full features
3. Detect thread format and match it
4. Allow projects to choose their level

**Effort:** High (4-5 days)
**Risk:** Medium (complex, two code paths)
**Benefit:** Maximum flexibility

---

## 13. Recommendation

**I recommend Option A: Restore Full Features**

**Reasoning:**
1. That was the original plan (100% CLI parity)
2. Features aren't optional — they're core to the protocol
3. acpmonkey needs these features for migration
4. Reference code exists (straightforward restoration)
5. Better to do it right than ship incomplete library

**Next Steps:**
1. Create detailed restoration plan
2. Implement features one by one
3. Update tests to cover structured entries
4. Verify against real acpmonkey threads
5. Update documentation

**Timeline:**
- Day 1: Entry structure + templates
- Day 2: Roles + agent registry
- Day 3: Testing + documentation

---

## Questions for You (Jay)

1. **Did you realize these features were removed?**
   - If not, we should restore them
   - If yes, was there a reason?

2. **Is acpmonkey the primary user?**
   - If yes, we need full feature parity
   - If no, who is the target user?

3. **What's the priority?**
   - Quick library (keep simple version)?
   - Complete library (restore features)?
   - Future-proof library (hybrid approach)?

4. **Should we pause and reassess?**
   - Maybe the extraction wasn't the right approach?
   - Maybe acpmonkey should keep its watercooler.py?
   - Maybe we need different scope?

---

## Conclusion

The current watercooler-collab library is **incomplete** for its intended purpose. Critical structured collaboration features were removed during extraction, breaking the core value proposition.

**The library currently cannot:**
- Support structured entries (Type, Title)
- Track agent roles (planner, critic, implementer)
- Load custom templates
- Handle multi-agent registries
- Provide rich thread indexes
- Replace acpmonkey's watercooler.py

**We need to decide:**
- Restore features (Option A) - True library
- Accept as simplified tool (Option B) - Different product
- Build hybrid solution (Option C) - Maximum flexibility

I recommend **Option A** based on the original goal of "100% CLI parity" and the need for acpmonkey to adopt this library.

What would you like to do?
