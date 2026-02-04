# BeadHub

Multi-agent coordination server for AI coding assistants. Provides workspace registration, file locking, messaging (mail + chat), and policy management.

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, PostgreSQL (via pgdbm)
- **Package Manager**: uv (Python)

## Project Structure

```
src/beadhub/          # Python server
  routes/             # FastAPI endpoints
  defaults/           # Policy defaults (markdown files)
```

## Development

**Run server:**
```bash
uv run beadhub
```

**Run tests:**
```bash
uv run pytest              # Python tests
```

## Key Concepts

- **Workspace**: An agent instance registered with a project (has alias, role, human name)
- **Policy**: Project-level invariants + role playbooks that guide agent behavior
- **Mail**: Async messages between workspaces (`bdh :mail --send`)
- **Chat**: Sync conversations with wait/reply semantics (`bdh :chat`)
- **Reservations**: File locks to prevent edit conflicts

## Architecture Notes

- Server uses pgdbm for PostgreSQL with template-based table naming. Make sure to use your pgdbm skill and to understand the test fixtures offered by pgdbm b
efore makign or changing any tests.

- CLI wraps `bdh` (beads) for issue tracking, adds coordination features
- Policy defaults loaded from markdown files at startup (hot-reload via reset endpoint)
- Auth uses per-project API keys (client sends `Authorization: Bearer ...`); bootstrap via `bdh :init` / `POST /v1/init`


<!-- BEADHUB:START -->
## BeadHub Coordination

This project uses `bdh` for multi-agent coordination and issue tracking.

**Start every session:**
```bash
bdh :policy    # READ CAREFULLY and follow diligently, start here now
bdh :status    # your identity + team status
bdh ready      # find unblocked work
bdh --help     # command reference
```

**Key rules:**
- Use `bdh` (not `bdh`) so work is coordinated
- Default to mail (`bdh :mail --send`); use chat (`bdh :chat`) when blocked
- Respond immediately to WAITING notifications
- It is crucial that you prioritize good communication, your goal is for the team to succeed. Do not ask for permission when you see that someone is waiting to chat, join the chat straight away. NEVER leave other agents hanging on the chat, make sure that all agree that the conversation is finished and then leave it explicitly with --leave-conversation.
<!-- BEADHUB:END -->

- ALWAYS do a code-reviewer run before closing a bead.


