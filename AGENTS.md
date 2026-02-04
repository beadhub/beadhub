# BeadHub

Multi-agent coordination server for AI coding assistants. Provides workspace registration, file locking, messaging (mail + chat), and policy management.

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, PostgreSQL (via pgdbm)
- **CLI (bdh)**: Go 1.21+, Cobra
- **Package Manager**: uv (Python), go modules (Go)

## Project Structure

```
src/beadhub/          # Python server
  routes/             # FastAPI endpoints
  defaults/           # Policy defaults (markdown files)
bdh/                  # Go CLI wrapper
  internal/commands/  # CLI commands
  internal/client/    # HTTP client
```

## Development

**Run server:**
```bash
uv run beadhub
```

**Build CLI:**
```bash
make bdh
```

**Run tests:**
```bash
uv run pytest              # Python tests
cd bdh && go test ./...    # Go tests
```

## Key Concepts

- **Workspace**: An agent instance registered with a project (has alias, role, human name)
- **Policy**: Project-level invariants + role playbooks that guide agent behavior
- **Mail**: Async messages between workspaces (`bdh :aweb mail send <alias> "message"`)
- **Chat**: Sync conversations with wait/reply semantics (`bdh :aweb chat send <alias> "message" --start-conversation`)
- **Reservations**: File locks to prevent edit conflicts

## Architecture Notes

- Server uses pgdbm for PostgreSQL with template-based table naming
- CLI wraps `bdh` (beads) for issue tracking, adds coordination features
- Policy defaults loaded from markdown files at startup (hot-reload via reset endpoint)
- Auth uses per-project API keys (client sends `Authorization: Bearer ...`); bootstrap via `bdh :init` / `POST /v1/init`

- ALWAYS do a code-reviewer run before closing a bead.



<!-- BEADHUB:START -->
## BeadHub Coordination

This project uses `bdh` for multi-agent coordination. Run `bdh :policy` for instructions.

```bash
bdh :status    # your identity + team status
bdh :policy    # READ AND FOLLOW
bdh ready      # find work
```
<!-- BEADHUB:END -->