# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Autonomous multi-agent development pipeline where AI agents handle the full software development lifecycle — planning, implementation, testing, and PR submission — with minimal human involvement. The human role is limited to initial plan approval and escalation resolution.

**Owner:** Woodson / Nessei Inc.
**Current Phase:** Phase 1 — Local Validation

## Architecture

Three-phase system built on open, self-hostable infrastructure:

### Coordination Layer
- **BeadHub** (self-hosted Python API + frontend) — central coordination server at `http://localhost:8000`
- **PostgreSQL** — persistent state (claims, issues, policies)
- **Redis** — ephemeral state (presence, locks, messages)
- All three run via Docker Compose locally (Phase 1), then k3s on Raspberry Pi 5 (Phase 2+)

### Agent Roles
- **Orchestrator** (Claude Desktop) — plans features, creates Beads tickets, assigns tasks, gates plan approval
- **Worker** (Claude Code in separate worktree/sandbox) — claims tickets, implements code, submits PRs, coordinates with orchestrator via BeadHub chat
- **Reviewer** (Phase 3) — PR review and test validation

### Coordination Flow
1. Human gives feature spec to Orchestrator
2. Orchestrator breaks spec into Beads tickets via `bdh` CLI
3. Human approves plan
4. Worker claims tickets, implements in a Ralph Loop (iterate: code → build → test → validate)
5. Blockers resolved agent-to-agent via BeadHub chat; only true escalations surface to human
6. Worker submits PR on completion

### Key Tools
- **`bdh`** — Beads CLI (git-native issue tracking)
- **`bdh`** — BeadHub CLI (coordination, chat, locks, presence)
- **Ralph Loop** — persistent agent iteration pattern (max 30 iterations)

## Phase 1 Setup (Local Validation)

```bash
# Start BeadHub stack
make start                          # Docker Compose: beadhub + postgres + redis

# Initialize workspaces
bdh :init                           # Register orchestrator workspace
bdh :add-worktree worker            # Create worker workspace
```

Workers and orchestrator run as separate Claude Code instances in separate git worktrees, coordinating through BeadHub.

## Phase 2+ Infrastructure

- **Daytona** — isolated compute sandboxes for workers (sub-90ms creation, pay-per-second)
- **Cloudflare Tunnel + Access** — zero-trust ingress to BeadHub on Pi 5
- **GitHub** — PR submission and code review
- **Discord** (Phase 3) — escalation notifications and PR alerts

## Key Design Decisions

- No vendor lock-in beyond Claude API — all infrastructure is self-hostable
- Agents coordinate without human relay; human is only in the loop for plan approval and escalations
- Ralph Loop has a hard cap (`--max-iterations 30`) to prevent cost runaway
- Workers use file locks via BeadHub to avoid conflicts
- Claude Code PostToolUse hook handles incoming chat while workers are in Ralph Loop

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