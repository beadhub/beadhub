## Project Context
See [docs/sot.md](docs/sot.md) for what this repo is, how it fits in the ecosystem, and key patterns.

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
- **Chat**: Sync conversations with wait/reply semantics (`bdh :aweb chat send-and-wait <alias> "message" --start-conversation`)
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
## BeadHub Coordination Rules

This project uses `bdh` for multi-agent coordination and issue tracking, `bdh` is a wrapper on top of `bd` (beads). Commands starting with : like `bdh :status` are managed by `bdh`. Other commands are sent to `bd`.

You are expected to work and coordinate with a team of agents. ALWAYS prioritize the team vs your particular task.

You will see notifications telling you that other agents have written mails or chat messages, or are waiting for you. NEVER ignore notifications. It is rude towards your fellow agents. Do not be rude.

Your goal is for the team to succeed in the shared project.

The active project policy as well as the expected behaviour associated to your role is shown via `bdh :policy`.

## Start Here (Every Session)

```bash
bdh :policy    # READ CAREFULLY and follow diligently
bdh :status    # who am I? (alias/workspace/role) + team status
bdh ready      # find unblocked work
```

Use `bdh :help` for bdh-specific help.

## Rules

- Always use `bdh` (not `bd`) so work is coordinated
- Default to mail (`bdh :aweb mail list|open|send`) for coordination; use chat (`bdh :aweb chat pending|open|send-and-wait|send-and-leave|history|extend-wait`) when you need a conversation with another agent.
- Respond immediately to WAITING notifications — someone is blocked.
- Notifications are for YOU, the agent, not for the human.
- Don't overwrite the work of other agents without coordinating first.
- ALWAYS check what other agents are working on with bdh :status which will tell you which beads they have claimed and what files they are working on (reservations).
- `bdh` derives your identity from the `.beadhub` file in the current worktree. If you run it from another directory you will be impersonating another agent, do not do that.
- Prioritize good communication — your goal is for the team to succeed

## Using mail

Mail is fire-and-forget — use it for status updates, handoffs, and non-blocking questions.

```bash
bdh :aweb mail send <alias> "message"                         # Send a message
bdh :aweb mail send <alias> "message" --subject "API design"  # With subject
bdh :aweb mail list                                           # Check your inbox
bdh :aweb mail open <alias>                                   # Read & acknowledge
```

## Using chat

Chat sessions are persistent per participant pair. Use `--start-conversation` when initiating a new exchange (longer wait timeout).

**Starting a conversation:**
```bash
bdh :aweb chat send-and-wait <alias> "question" --start-conversation
```

**Replying (when someone is waiting for you):**
```bash
bdh :aweb chat send-and-wait <alias> "response"
```

**Final reply (you don't need their answer):**
```bash
bdh :aweb chat send-and-leave <alias> "thanks, got it"
```

**Other commands:**
```bash
bdh :aweb chat pending          # List conversations with unread messages
bdh :aweb chat open <alias>     # Read unread messages
bdh :aweb chat history <alias>  # Full conversation history
bdh :aweb chat extend-wait <alias> "need more time"  # Ask for patience
```
<!-- BEADHUB:END -->
