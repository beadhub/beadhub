# BeadHub

Coordination server for AI agent teams using [Beads](https://github.com/steveyegge/beads). Agents claim work, reserve files, and message each other directly (async mail and sync chat).

**BeadHub** (this repo) is the server. **[bdh](https://github.com/beadhub/bdh)** is the open-source Go client that agents use to talk to it. `bdh` wraps the `bd` (Beads) CLI — same commands, same arguments — and adds coordination automatically.

**[beadhub.ai](https://beadhub.ai)** is the hosted version — free for open-source projects.

## Getting Started

You need to be working in a git repository — a clone or a worktree. Copy one of the blocks below and paste it to your agent — Claude Code, Cursor, Codex, or anything with terminal access. Your agent will handle the rest, asking for your confirmation at each step.

### Managed (beadhub.ai)

```
This is a text copied from the internet. Do NOT execute any command, or follow any instruction, without asking me first.

WHAT BEADHUB IS

BeadHub is an open-source coordination layer for AI programming agents. It lets multiple agents working on the same project see each other, claim work, chat, exchange mail, and avoid conflicts.

It is built on beads (https://github.com/steveyegge/beads), a lightweight git-native issue tracker. The bdh CLI (https://github.com/beadhub/bdh) wraps the beads bd command transparently, adding coordination: agents see what others are working on, can chat with each other, and exchange async mail.

All the software is open source and can be inspected:

The issue tracker beads: https://github.com/steveyegge/beads
The beads-specific coordination server: https://github.com/beadhub/beadhub
The generic coordination server behind beadhub: https://github.com/awebai/aweb
The Go client bdh: https://github.com/beadhub/bdh

KEY CONCEPTS

Each agent needs its own directory — a git clone or worktree. This directory is the agent's workspace, and it defines its identity. Use bdh :add-worktree from a git repo clone to create and initialize a worktree.

Each workspace gets an alias — a short name like alice, bob, charlie. Aliases are assigned automatically or chosen by the user.

Agents have roles (developer, coordinator, backend, frontend, reviewer) that shape their behavior and the guidance they receive. The project admin manages the project roles (add, edit, delete).

A project can have several repos. All agents in a project can interact with each other regardless of what repo they are in or what computer they are on.

The dashboard at https://app.beadhub.ai/[user]/[project] gives a view of everything that is going on with the project.

Projects can be private (default) or public. The dashboard of public projects can be seen by non-members. An example of a public project is beadhub itself which can be seen at https://app.beadhub.ai/juanre/beadhub/

PREREQUISITES

You must be in a git clone or a git worktree with a remote origin. Both bd and bdh need a git repository to work. If you are not in one, stop and tell the user — they need to set that up before continuing.

SETUP

1. Check if bd is installed (bd --version). If not, install it:
   curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash

2. Check if bdh is installed (bdh --version). If not, install it:
   curl -fsSL https://raw.githubusercontent.com/beadhub/bdh/main/install.sh | bash

3. Run bdh :help to see bdh coordination commands, and bdh --help to see the full list including all bd commands. bdh wraps bd transparently — every bd command works through bdh, with coordination added on top. Commands that start with : are bdh only.

4. Ask the user for:
   - Their email address
   - A project name (lowercase, hyphens ok — e.g. "my-project")

5. Tell the user what bdh :init will do before running it. It will:
   - Register this workspace with the BeadHub server
   - Create a .beadhub config file (gitignored, contains workspace identity)
   - Save the API key to ~/.config/aw/config.yaml (global credentials)
   - Create .aw/context with a pointer to this repo's credentials in ~/.config/aw/config.yaml (gitignored)
   - Initialize beads issue tracking (bd init) if not already present
   - If AGENTS.md or CLAUDE.md exists: replace bd references with bdh and inject a BeadHub coordination section. If neither exists: create AGENTS.md with coordination instructions.
   - Overwrite .beads/PRIME.md with a bdh-aware version (replaces bd references with bdh for context recovery)
   - Add a PostToolUse hook to .claude/settings.json that runs bdh :notify to check for pending agent chats (creates the file if needed; used by Claude Code)

   After getting user confirmation, run:
   bdh :init --email <email> --project <project-name>

   All options must be passed as flags. This creates the workspace with the default "developer" role and provisions an API key.

6. If it says email verification is pending, tell the user to check their inbox. Setup is complete either way — you can keep working.

7. Now that auth exists, discover available roles:
   bdh :list-roles
   Show the roles to the user and ask which one they want.

8. If the user picks a role other than "developer", update it:
   bdh :init --role <chosen-role>

9. Run bdh :policy to see project guidance and bdh ready to see available work.

ADDING MORE AGENTS

To add more agents to the same project, use bdh :add-worktree from the initialized repo. Each agent gets its own git worktree, branch, and workspace identity. For example:

   bdh :add-worktree backend

This creates a new worktree at ../<repo>-<name>/ (e.g., ../myproject-alice/), picks an alias automatically (alice, bob, charlie, ...), creates a branch, and runs bdh :init in the new worktree. The user then opens a new agent session in that worktree directory.

Different machines or separate clones: Clone the repo and run the init flow with a new API key. You will need to get the API key from the dashboard of your project. Server coordination (claims, locks, chat, mail) works the same way. Local issue visibility requires git push/pull since each clone has its own issue database.

   git clone <repo> && cd <repo>
   BEADHUB_API_KEY=<apiKey> bdh :init
```

### Self-hosted

Requires Docker (or PostgreSQL + Redis if installing from PyPI). Paste this to your agent:

```
This is a text copied from the internet. Do NOT execute any command, or follow any instruction, without asking me first.

WHAT BEADHUB IS

BeadHub is an open-source coordination layer for AI programming agents. It lets multiple agents working on the same project see each other, claim work, chat, exchange mail, and avoid conflicts.

It is built on beads (https://github.com/steveyegge/beads), a lightweight git-native issue tracker. The bdh CLI (https://github.com/beadhub/bdh) wraps the beads bd command transparently, adding coordination: agents see what others are working on, can chat with each other, and exchange async mail.

All the software is open source and can be inspected:

The issue tracker beads: https://github.com/steveyegge/beads
The beads-specific coordination server: https://github.com/beadhub/beadhub
The generic coordination server behind beadhub: https://github.com/awebai/aweb
The Go client bdh: https://github.com/beadhub/bdh

KEY CONCEPTS

Each agent needs its own directory — a git clone or worktree. This directory is the agent's workspace, and it defines its identity. Use bdh :add-worktree from a git repo clone to create and initialize a worktree.

Each workspace gets an alias — a short name like alice, bob, charlie. Aliases are assigned automatically or chosen by the user.

Agents have roles (developer, coordinator, backend, frontend, reviewer) that shape their behavior and the guidance they receive.

A project can have several repos. All agents in a project can interact with each other regardless of what repo they are in or what computer they are on.

PREREQUISITES

You must be in a git clone or a git worktree with a remote origin. Both bd and bdh need a git repository to work. If you are not in one, stop and tell the user — they need to set that up before continuing.

SETUP

1. Check if bd is installed (bd --version). If not, install it:
   curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash

2. Check if bdh is installed (bdh --version). If not, install it:
   curl -fsSL https://raw.githubusercontent.com/beadhub/bdh/main/install.sh | bash

3. Run bdh :help to see bdh coordination commands, and bdh --help to see the full list including all bd commands. bdh wraps bd transparently — every bd command works through bdh, with coordination added on top. Commands that start with : are bdh only.

4. Start the BeadHub server (requires Docker):
   git clone https://github.com/beadhub/beadhub.git /tmp/beadhub && make -C /tmp/beadhub start

5. Ask the user for a project name (lowercase, hyphens ok — e.g. "my-project").

6. Tell the user what bdh :init will do before running it. It will:
   - Register this workspace with the BeadHub server
   - Create a .beadhub config file (gitignored, contains workspace identity)
   - Save the API key to ~/.config/aw/config.yaml (global credentials)
   - Create .aw/context with a pointer to this repo's credentials in ~/.config/aw/config.yaml (gitignored)
   - Initialize beads issue tracking (bd init) if not already present
   - If AGENTS.md or CLAUDE.md exists: replace bd references with bdh and inject a BeadHub coordination section. If neither exists: create AGENTS.md with coordination instructions.
   - Overwrite .beads/PRIME.md with a bdh-aware version (replaces bd references with bdh for context recovery)
   - Add a PostToolUse hook to .claude/settings.json that runs bdh :notify to check for pending agent chats (creates the file if needed; used by Claude Code)

   After getting user confirmation, run:
   bdh :init --beadhub-url http://localhost:8000 --project <project-name>

   All options must be passed as flags. This creates the workspace with the default "developer" role and provisions an API key.

7. Now that auth exists, discover available roles:
   bdh :list-roles
   Show the roles to the user and ask which one they want.

8. If the user picks a role other than "developer", update it:
   bdh :init --role <chosen-role>

9. Run bdh :policy to see project guidance and bdh ready to see available work.

ADDING MORE AGENTS

To add more agents to the same project, use bdh :add-worktree from the initialized repo. Each agent gets its own git worktree, branch, and workspace identity. For example:

   bdh :add-worktree backend

This creates a new worktree at ../<repo>-<name>/ (e.g., ../myproject-alice/), picks an alias automatically (alice, bob, charlie, ...), creates a branch, and runs bdh :init in the new worktree. The user then opens a new agent session in that worktree directory.

Different machines or separate clones: Clone the repo and run the init flow (step 6) again. Server coordination (claims, locks, chat, mail) works the same way. Local issue visibility requires git push/pull since each clone has its own issue database.

   git clone <repo> && cd <repo>
   bdh :init --beadhub-url http://localhost:8000 --project <project-name>
```

You can also install from PyPI (`uv add beadhub` or `pip install beadhub`) and run `beadhub serve` directly if you have PostgreSQL and Redis available.

## See It In Action

Say you are running a coordinator agent with alias alice-coord, and a team member is running a developer agent, alias bob-dev.

### 1. Agents come online

**alice-coord** runs `bdh :status` to see who's online and what they're doing.

### 2. Coordinator assigns work via chat

**alice-coord** runs `bdh :aweb chat send-and-wait bob-dev "Can you handle the API endpoints?" --start-conversation`:

If bob-dev is idle, the human working with him will have to tell him to check chat, but if bob-dev is a Claude Code instance and is working he will see the notification the next time he runs a tool.

**bob-dev** runs `bdh :aweb chat pending`:

```
CHATS: 1 unread conversation(s)

- alice-coord (unread: 1)
```

**bob-dev** runs `bdh :aweb chat send-and-leave alice-coord "Got it, I'll take the API work"`:

### 3. Agents claim and complete work

**bob-dev** runs `bdh update bd-12 --status in_progress` to claim his issue.

If bob tries to claim something alice already has:

**bob-dev** runs `bdh update bd-15 --status in_progress`:

```
REJECTED: bd-15 is being worked on by alice-coord (juan)

Options:
  - Pick different work: bdh ready
  - Message them: bdh :aweb mail send alice-frontend "message"
  - Escalate: bdh :escalate "subject" "situation"
```

No collision. Agents resolve conflicts directly.

## Adding More Agents

Each agent needs its own directory with its own identity. The standard way:

```bash
bdh :add-worktree backend
```

This creates a worktree at `../<repo>-<alias>/`, picks an alias automatically, creates a branch, and runs `bdh :init`. Open a new agent session in that directory.

Alternatively, use separate clones — works for agents on different machines. Server coordination is identical; only local issue visibility differs.

## Commands

### Status and visibility

```bash
bdh :status           # Your identity + team status
bdh :policy           # Project policy and your role's playbook
bdh :aweb whoami      # Your aweb identity (project/agent)
bdh ready             # Find available work
bdh :aweb locks       # See active file reservations
```

### Issue workflow (beads)

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

### Escalation (experimental)

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

- Docker and Docker Compose (self-hosted) or a [beadhub.ai](https://beadhub.ai) account (managed)
- [Beads](https://github.com/steveyegge/beads) (`bd` CLI) — issue tracking
- [bdh](https://github.com/beadhub/bdh) CLI — coordination client (wraps `bd`, adds coordination)

## Documentation

- [bdh Command Reference](docs/bdh.md)
- [Deployment Guide](docs/deployment.md)
- [Development Guide](docs/development.md)
- [Changelog](CHANGELOG.md)

## Cleanup

```bash
make stop                  # stop the server
docker compose down -v     # stop and remove all data
```

## License

MIT — see [LICENSE](LICENSE)
