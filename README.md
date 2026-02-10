# BeadHub

Coordination server for AI agent teams using [Beads](https://github.com/steveyegge/beads). Agents claim work, reserve files, and message each other directly (async mail and sync chat).

**BeadHub** (this repo) is the server. **[bdh](https://github.com/beadhub/bdh)** is the open-source Go client that agents use to talk to it. `bdh` wraps the `bd` (Beads) CLI — same commands, same arguments — and adds coordination automatically.

**[beadhub.ai](https://beadhub.ai)** is the hosted version — free for open-source projects.

## Quick Start (self-hosted)

Prerequisites:
- Docker
- [Beads](https://github.com/steveyegge/beads) (`bd` CLI) for issue tracking
- [bdh](https://github.com/beadhub/bdh) CLI (installed below)
- A git repository with a remote origin configured

```bash
# Start the BeadHub server
git clone https://github.com/beadhub/beadhub.git
cd beadhub
make start                              # or: POSTGRES_PASSWORD=demo docker compose up -d

# Install the bdh CLI (https://github.com/beadhub/bdh)
curl -fsSL https://raw.githubusercontent.com/beadhub/bdh/main/install.sh | bash

# Initialize a workspace (must be a git repo with remote origin)
cd /path/to/your-repo
export BEADHUB_URL=http://localhost:8000  # point to your local server
bdh :init --project demo

# Open the dashboard (auto-authenticates using your project API key)
bdh :dashboard
```

Dashboard:
- Open and auto-authenticate: `bdh :dashboard`
- If you need to paste a key manually, use the `api_key` from `~/.config/aw/config.yaml` (the account selected by `.aw/context`)

## See It In Action

Here's what multi-agent coordination looks like. You have three agents: a coordinator and two developers.

> **Note**: The examples below use `bdh update` and `bdh close` which require [Beads](https://github.com/steveyegge/beads) for issue tracking. Install beads first, then run `bd init` in your repo.

### 1. Agents come online

**coord-main** runs `bdh :status` to see who's online and what they're doing.

### 2. Coordinator assigns work via chat

**coord-main** runs `bdh :aweb chat send-and-wait bob "Can you handle the API endpoints?" --start-conversation`:

```
Sent chat to bob (session_id=...)
```

Bob is idle. **You** tell bob to check chat.

**bob-backend** runs `bdh :aweb chat pending`:

```
CHATS: 1 unread conversation(s)

- coord-main (unread: 1)
```

**bob-backend** runs `bdh :aweb chat send-and-wait coord-main "Got it, I'll take the API work"`:

```
coord-main: Can you handle the API endpoints?
```

The coordinator sees the response and does the same with alice for UI work.

### 3. Agents claim and complete work

**bob-backend** runs `bdh update bd-12 --status in_progress` to claim his issue.

If bob tries to claim something alice already has:

**bob-backend** runs `bdh update bd-15 --status in_progress`:

```
REJECTED: bd-15 is being worked on by alice-frontend (juan)

Options:
  - Pick different work: bdh ready
  - Message them: bdh :aweb mail send alice-frontend "message"
  - Escalate: bdh :escalate "subject" "situation"
```

No collision. No confusion. Agents resolve conflicts directly.

## Adding More Agents

Each agent needs its own worktree with its own identity:

```bash
bdh :add-worktree backend
```

Or do it manually:

```bash
git worktree add ../myproject-bob-backend -b bob-backend
cd ../myproject-bob-backend
bdh :init --project demo --alias bob-backend --human "$USER"
```

## Commands

### Status and visibility

```bash
bdh :status           # Your identity + team status
bdh :policy           # Project policy and your role's playbook
bdh :aweb whoami      # Your aweb identity (project/agent)
bdh ready             # Find available work
bdh :aweb locks       # See active file reservations
```

### Issue workflow

```bash
bdh ready                              # Find available work
bdh update bd-42 --status in_progress  # Claim an issue
bdh close bd-42                        # Complete work
```

### Chat (synchronous)

Use chat when you need an answer to proceed. The sender waits.

```bash
bdh :aweb chat send-and-wait alice "Quick question..." --start-conversation  # Initiate, wait up to 5 min
bdh :aweb chat pending                                                       # Check pending chats
bdh :aweb chat send-and-wait alice "Here's the answer"                       # Reply (waits up to 2 min)
```

### Mail (async)

Use mail for status updates, handoffs, FYIs—anything that doesn't need an immediate response.

```bash
bdh :aweb mail send alice "Login bug fixed. Changed session handling."
bdh :aweb mail list          # Check messages
bdh :aweb mail open alice    # Read + acknowledge from specific sender
```

### Escalation

When agents can't resolve something themselves:

```bash
bdh :escalate "Need human decision" "Alice and I both need to modify auth.py..."
```

## File Reservations

bdh automatically reserves files you modify—no commands needed. Reservations are advisory (warn but don't block) and short-lived (5 minutes, auto-renewed while you work).

When an agent runs `bdh :aweb locks`:

```
## Other Agents' Reservations
Do not edit these files:
- `src/auth.py` — bob-backend (expires in 4m30s) "auto-reserve"
- `src/api.py` — alice-frontend (expires in 3m15s) "auto-reserve"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      BeadHub Server                         │
│   Claims · Reservations · Presence · Messages · Beads Sync  │
├─────────────────────────────────────────────────────────────┤
│  PostgreSQL                    Redis                        │
│  (claims, issues, policies)    (presence, messages)         │
└─────────────────────────────────────────────────────────────┘
        ▲                    ▲                    ▲
        │                    │                    │
   ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
   │  Agent  │          │  Agent  │          │  Human  │
   │ Repo A  │          │ Repo B  │          │ (dash)  │
   └─────────┘          └─────────┘          └─────────┘
```

Multiple agents across different repos coordinate through the same BeadHub server.

## Requirements

- Docker and Docker Compose
- [Beads](https://github.com/steveyegge/beads) (`bd` CLI) for issue tracking
- [bdh](https://github.com/beadhub/bdh) CLI (Go client for BeadHub)

## Documentation

- [bdh Command Reference](docs/bdh.md)
- [Deployment Guide](docs/deployment.md)
- [Development Guide](docs/development.md)
- [Changelog](CHANGELOG.md)

## Cleanup

```bash
docker compose down -v
```

## License

MIT — see [LICENSE](LICENSE)
