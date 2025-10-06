# CLI Parity Audit: watercooler-collab vs acpmonkey

**Date:** 2025-10-06
**Status:** Simplified API (intentional deviation from original plan)

## Summary

The watercooler-collab library has **intentionally simplified** the CLI compared to acpmonkey's watercooler.py. The implementation provides core collaboration functionality while removing complexity around roles, entry types, and rigid templates.

## Design Philosophy

**acpmonkey approach:** Structured entries with roles, types, titles, and template-driven formatting
**watercooler-collab approach:** Flexible, minimal API focused on quick collaboration

## Command-by-Command Comparison

### ✅ init-thread
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| topic (positional) | ✓ | ✓ | ✓ Match |
| --threads-dir | ✓ | ✓ | ✓ Match |
| --ball | ✓ | ✓ | ✓ Match |
| --status | ✗ | ✓ | ⚠️ Enhanced |
| --title | ✗ | ✓ | ⚠️ Enhanced |
| --body | ✗ | ✓ | ⚠️ Enhanced |
| --owner | ✓ | ✗ | ⚠️ Removed |
| --participants | ✓ | ✗ | ⚠️ Removed |
| --templates-dir | ✓ | ✗ | ⚠️ Removed |
| --agents-file | ✓ | ✗ | ⚠️ Removed |

**Assessment:** Simplified - removed owner/participants tracking, added direct body support

### ⚠️ append-entry
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| topic (positional) | ✓ | ✓ | ✓ Match |
| --threads-dir | ✓ | ✓ | ✓ Match |
| --body | via --body-file | ✓ (direct or @file) | ⚠️ Enhanced |
| --author | via --agent | ✓ | ⚠️ Renamed |
| --bump-status | via --status | ✓ | ⚠️ Renamed |
| --bump-ball | via --ball | ✓ | ⚠️ Renamed |
| --agent | ✓ (required) | ✗ | ⚠️ Removed |
| --role | ✓ (required) | ✗ | ⚠️ Removed |
| --title | ✓ (required) | ✗ | ⚠️ Removed |
| --type | ✓ (Note/Plan/Decision/PR/Closure) | ✗ | ⚠️ Removed |

**Assessment:** Major simplification - removed structured entry metadata

### ⚠️ say
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| topic (positional) | ✓ | ✓ | ✓ Match |
| --threads-dir | ✓ | ✓ | ✓ Match |
| --body | via --body-file | ✓ (required, direct or @file) | ⚠️ Enhanced |
| --author | via --agent | ✓ | ⚠️ Simplified |
| --title | ✓ (required) | ✗ | ⚠️ Removed |
| --type | ✓ (Note/Plan/etc.) | ✗ | ⚠️ Removed |
| --status | ✓ | ✗ | ⚠️ Removed |
| --ball | ✓ | ✗ | ⚠️ Removed |
| --agent | ✓ | ✗ | ⚠️ Removed |
| --role | ✓ | ✗ | ⚠️ Removed |

**Assessment:** Greatly simplified - just topic + body + optional author

### ⚠️ ack
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| topic (positional) | ✓ | ✓ | ✓ Match |
| --threads-dir | ✓ | ✓ | ✓ Match |
| --note | via --body-file | ✓ | ⚠️ Simplified |
| --author | via --agent | ✓ | ⚠️ Simplified |
| --title | ✓ | ✗ | ⚠️ Removed |
| --type | ✓ | ✗ | ⚠️ Removed |
| --status | ✓ | ✗ | ⚠️ Removed |
| --ball | ✓ | ✗ | ⚠️ Removed |

**Assessment:** Simplified - just topic + optional note + optional author

### ⭐ handoff (NEW)
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| topic (positional) | ✗ | ✓ | ⭐ New |
| --threads-dir | ✗ | ✓ | ⭐ New |
| --author | ✗ | ✓ | ⭐ New |
| --note | ✗ | ✓ | ⭐ New |

**Assessment:** NEW command - automatic ball flipping to counterpart

### ✅ set-status
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| topic (positional) | ✓ | ✓ | ✓ Match |
| --status | ✓ (required) | ✓ (positional) | ⚠️ Different |
| --threads-dir | ✓ | ✓ | ✓ Match |

**Assessment:** Minor difference - status is positional arg instead of flag

### ✅ set-ball
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| topic (positional) | ✓ | ✓ | ✓ Match |
| --ball | ✓ (required) | ✓ (positional) | ⚠️ Different |
| --threads-dir | ✓ | ✓ | ✓ Match |

**Assessment:** Minor difference - ball is positional arg instead of flag

### ✅ list
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| --threads-dir | ✓ | ✓ | ✓ Match |
| --open-only | ✗ | ✓ | ⭐ New |
| --closed | ✗ | ✓ | ⭐ New |
| --ball | ✓ (filter) | ✗ | ⚠️ Removed |
| --status | ✓ (filter) | ✗ | ⚠️ Removed |

**Assessment:** Different filtering approach - open/closed vs ball/status

### ✅ reindex
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| --threads-dir | ✓ | ✓ | ✓ Match |
| --out | ✗ | ✓ | ⭐ New |
| --open-only | ✗ | ✓ | ⭐ New |
| --closed | ✗ | ✓ | ⭐ New |

**Assessment:** Enhanced - added output file option and filtering

### ✅ web-export
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| --threads-dir | ✓ | ✓ | ✓ Match |
| --out | ✗ | ✓ | ⭐ New |
| --open-only | ✗ | ✓ | ⭐ New |
| --closed | ✗ | ✓ | ⭐ New |

**Assessment:** Enhanced - added output file option and filtering

### ✅ search
| Feature | acpmonkey | watercooler-collab | Status |
|---------|-----------|-------------------|--------|
| query (positional) | ✓ | ✓ | ✓ Match |
| --threads-dir | ✓ | ✓ | ✓ Match |
| --context | ✓ | ✗ | ⚠️ Removed |

**Assessment:** Simplified - removed context lines feature

## Key Differences Summary

### Removed Features
1. **Entry structure:** No --role, --type, --title in say/ack/append
2. **Agent registry:** No --agents-file parameter
3. **Templates:** No --templates-dir parameter
4. **Filtering:** Removed --ball and --status filters from list
5. **Context:** Removed --context from search

### Added Features
1. **handoff command:** Automatic ball flipping
2. **Filtering:** Added --open-only and --closed flags
3. **Direct body:** --body accepts text or @file
4. **Output control:** --out flag for reindex/web-export
5. **Initial content:** --body flag for init-thread

### Philosophy Changes
- **Flexibility over structure:** Removed rigid entry templates
- **Simplicity over features:** Fewer flags, clearer API
- **Quick notes:** say/ack are one-liners, not structured entries

## Compatibility Assessment

**Can acpmonkey migrate to watercooler-collab?**

⚠️ **Partial** - Thread format is compatible, but CLI usage patterns differ significantly:

- ✓ Thread files (.md) are compatible
- ✓ Headers (Status, Ball, Updated) match
- ✓ Basic operations (init, set-status, set-ball) work
- ⚠️ Entry format is different (no structured metadata)
- ⚠️ say/ack/append have different APIs
- ⚠️ No agent/role tracking

**Recommendation:** This is a **simplified alternative**, not a drop-in replacement. Suitable for new projects or users who prefer minimal structure.

## Action Items

- [x] Document differences in this audit
- [ ] Update STATUS.md to note intentional API divergence
- [ ] Consider adding migration notes for acpmonkey users
- [ ] Evaluate if we want to add --context back to search
- [ ] Consider if filtering by --ball/--status in list is needed

## Conclusion

The watercooler-collab library has **intentionally diverged** from the original implementation plan to create a simpler, more flexible collaboration tool. This is a valid design choice that prioritizes ease of use over feature completeness.

The "100% CLI parity" goal from the original plan was **not achieved**, but was replaced with a **simplified, enhanced API** that serves the core use case more effectively.
