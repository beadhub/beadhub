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
- **Mail**: Async messages between workspaces (`bdh :aweb mail send <alias> "message"`)
- **Chat**: Sync conversations with wait/reply semantics (`bdh :aweb chat send <alias> "message" --start-conversation`)
- **Reservations**: File locks to prevent edit conflicts

## Architecture Notes

- Server uses pgdbm for PostgreSQL with template-based table naming. Make sure to use your pgdbm skill and to understand the test fixtures offered by pgdbm b
efore makign or changing any tests.

- CLI wraps `bdh` (beads) for issue tracking, adds coordination features. It lives in the separate https://github.com/beadhub/bdh repo.
- Policy defaults loaded from markdown files at startup (hot-reload via reset endpoint)
- Auth uses per-project API keys (client sends `Authorization: Bearer ...`); bootstrap via `bdh :init` / `POST /v1/init`

- ALWAYS do a code-reviewer run before closing a bead.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bdh sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

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
- Use `bdh` (not `bd`) so work is coordinated
- Default to mail (`bdh :aweb mail send <alias> "message"`); use chat (`bdh :aweb chat`) when blocked
- Respond immediately to WAITING notifications
- Prioritize good communication — your goal is for the team to succeed
- Before saying "done", follow the session close protocol in `bdh :policy` (includes `git push`)
<!-- BEADHUB:END -->
