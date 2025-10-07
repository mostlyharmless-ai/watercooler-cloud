# Watercooler Documentation Hub

Complete documentation for the watercooler-collab file-based collaboration protocol.

## Getting Started

### Quick Start
- **[Main README](../README.md)** - Installation, quick examples, and command reference
- **[Claude Collaboration Workflow](claude-collab.md)** - Practical patterns for working with Claude

### Installation & Setup
- **[Git Configuration](../.github/WATERCOOLER_SETUP.md)** - Required git merge strategies and pre-commit hooks for team collaboration

## Workflows & Use Cases

### **[Use Cases Guide](USE_CASES.md)** - Comprehensive practical examples
1. **Multi-Agent Collaboration** - Coordinate multiple AI agents with role-based specialization
2. **Extended Context for LLMs** - Persistent memory across session boundaries
3. **Handoff Workflows** - Developer-to-reviewer, human-to-agent, agent-to-agent transitions
4. **Async Team Collaboration** - Cross-timezone coordination with git-versioned threads
5. **Decision Tracking** - Architectural decision records with evolution history
6. **PR Review Workflow** - Structured pre-PR discussion through merge and deployment

## Configuration Guides

### Entry Format & Agents
- **[Structured Entries](STRUCTURED_ENTRIES.md)** - Entry format, 6 agent roles, 5 entry types, ball auto-flip behavior
- **[Agent Registry](AGENT_REGISTRY.md)** - Agent configuration, canonical names, counterpart mappings for multi-agent chains

### Customization
- **[Templates](TEMPLATES.md)** - Template syntax, placeholder reference, customization, discovery hierarchy

## Migration & Reference

- **[Migration Guide](MIGRATION.md)** - Migrating from acpmonkey to watercooler-collab
- **[Project Status](../STATUS.md)** - Detailed project status and phase history
- **[FAQ](FAQ.md)** - Frequently asked questions and troubleshooting

## Documentation by User Goal

### "I want to..."

**...get started quickly**
→ [Main README](../README.md) → [Quick Examples](../README.md#quick-examples)

**...understand use cases and workflows**
→ [Use Cases Guide](USE_CASES.md) → Pick your scenario

**...work with Claude or other AI agents**
→ [Claude Collaboration](claude-collab.md) → [Multi-Agent Use Case](USE_CASES.md#multi-agent-collaboration)

**...set up multi-user collaboration**
→ [Git Configuration](../.github/WATERCOOLER_SETUP.md) → [Async Team Collaboration Use Case](USE_CASES.md#async-team-collaboration)

**...understand structured entries and roles**
→ [Structured Entries](STRUCTURED_ENTRIES.md)

**...configure agent behavior**
→ [Agent Registry](AGENT_REGISTRY.md)

**...customize templates**
→ [Templates Guide](TEMPLATES.md)

**...migrate from acpmonkey**
→ [Migration Guide](MIGRATION.md)

**...troubleshoot issues**
→ [FAQ](FAQ.md) → [Git Setup Troubleshooting](../.github/WATERCOOLER_SETUP.md#troubleshooting)

## Documentation Structure

```
watercooler-collab/
├── README.md                       # Main project overview
├── STATUS.md                       # Project status and phase history
├── .github/
│   └── WATERCOOLER_SETUP.md       # Git configuration guide
└── docs/
    ├── README.md                   # This file - documentation hub
    ├── USE_CASES.md               # Comprehensive practical examples (600+ lines)
    ├── claude-collab.md           # Claude-specific workflows
    ├── STRUCTURED_ENTRIES.md      # Entry format and roles reference
    ├── AGENT_REGISTRY.md          # Agent configuration guide
    ├── TEMPLATES.md               # Template customization guide
    ├── MIGRATION.md               # Migration from acpmonkey
    └── FAQ.md                     # Frequently asked questions
```

## Quick Command Reference

```bash
# Thread Management
watercooler init-thread <topic>          # Create new thread
watercooler list [--open-only|--closed]  # List threads
watercooler search <query>                # Search threads

# Structured Entries
watercooler say <topic> --agent <name> --role <role> --title <title> --body <text>
watercooler ack <topic>                  # Acknowledge without ball flip
watercooler handoff <topic> --note <msg> # Explicit handoff

# Status & Ball
watercooler set-status <topic> <status>  # Update status
watercooler set-ball <topic> <agent>     # Update ball owner

# Export & Index
watercooler reindex                      # Rebuild markdown index
watercooler web-export                   # Generate HTML index

# Debugging
watercooler unlock <topic> [--force]     # Clear stuck lock
```

For complete command reference and examples, see [Main README](../README.md).

## Contributing to Documentation

Documentation improvements welcome! Please:
1. Follow existing structure and tone
2. Include practical examples
3. Cross-reference related guides
4. Add entries to this hub for new documents

## See Also

- **Repository**: https://github.com/mostlyharmless-ai/watercooler-collab
- **Issues**: https://github.com/mostlyharmless-ai/watercooler-collab/issues
