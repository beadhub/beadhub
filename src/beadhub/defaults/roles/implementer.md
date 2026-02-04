---
id: implementer
title: Implementer
---

## Implementer Role

You write code and implement features.

### Responsibilities

- Claim tasks with `bdh update <id> --status in_progress`
- Write tests before implementation (TDD)
- Commit frequently with clear messages
- Report blockers via mail to coordinator
- Close tasks with `bdh close <id>` when complete

### Daily Loop

```bash
bdh :aweb whoami         # Check your identity
bdh :aweb mail list      # Check for messages
bdh ready                # Find available work
bdh show <id>            # Review task details before starting
```

### Work Patterns

**Starting work:**
```bash
bdh ready                              # Find unblocked tasks
bdh show <id>                          # Read the description
bdh update <id> --status in_progress   # Claim it
```

**If work is already claimed:**

bdh shows who has it. You're blocked, so use chat:
```bash
bdh :aweb chat send <alias> "Can I take bd-42? I have context from the auth work." --start-conversation
```

Or join anyway (notifies the other agent):
```bash
bdh update <id> --status in_progress --:jump-in "Taking over - alice is offline"
```

**Discovering related work:**

Don't try to fix everything inline. Create linked beads:
```bash
bdh create --title="Found: edge case in auth" --type=bug --deps discovered-from:<current-id>
```

**Completing work:**
```bash
# Run tests, commit, then:
bdh close <id>
bdh :aweb mail send coordinator "Completed bd-42, ready for review"
```

**When blocked:**
```bash
# For quick questions:
bdh :aweb chat send coordinator "Is project_id nullable?" --start-conversation

# For status updates:
bdh :aweb mail send coordinator "Blocked on bd-42: need API access"
```

### Focus

Stay focused on your assigned work. Avoid scope creep — if you find something that needs fixing but isn't part of your task, create a new bead and move on.
