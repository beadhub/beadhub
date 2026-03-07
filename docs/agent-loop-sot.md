# agent-loop — Source of Truth

Autonomous wrapper for AI coding agents in multi-agent coordination. Keeps agents continuously productive by dispatching work from bdh coordination state. Provider-agnostic: supports Claude Code now, designed for Codex and others.

## Problem

AI coding agents stop when they finish a task. They don't check mail, respond to chat, or pick up new work. With 10+ agents, a human can't babysit every terminal. `--dangerously-skip-permissions` removes the approval bottleneck but doesn't solve the idle problem.

## Solution

A wrapper that runs agents in a loop via their CLI's non-interactive mode (`claude -p`, etc.). Between runs, it queries bdh for coordination state and crafts the next prompt based on priority. All agents — including coordinators — run in the loop. Human interaction happens through terminal commands during runs and prompt injection between runs.

Implemented in Go as `bdh :run`, since bdh already has identity, API access, and coordination logic.

## Architecture

```
bdh :run (one per worktree)
  │
  ├── query bdh for coordination state
  │     chat pending?     → respond (includes message content)
  │     mail unread?      → respond (includes mail bodies)
  │     current claim?    → continue work
  │     bdh ready?        → pick up work
  │     nothing?          → skip, wait, re-poll
  │
  ├── compose prompt from layers
  │     base mission (CLI arg or config, persistent)
  │     + cycle instructions (from dispatch)
  │     + suffix (work or comms, from config)
  │
  ├── run agent CLI (claude -p, codex, etc.)
  │     parse structured output stream
  │     display formatted activity (bubbletea TUI)
  │     accept human commands (/stop, /wait, /quit, typed text)
  │
  ├── adaptive wait period
  │     or skip entirely if nothing needs attention
  │
  └── loop
```

### Identity

Inherited from the worktree. `.beadhub` defines alias, role, server. One worktree = one agent = one loop instance. `bdh :run` reads this directly — no configuration needed.

### Dispatch priority

Between runs, the wrapper queries bdh and selects the highest-priority action. Comms prompts include the actual message content so the agent can respond without re-fetching.

| Priority | Signal | Action | Wait |
|----------|--------|--------|------|
| 1 (urgent) | Chat pending | Respond to chat (includes last ~5 messages) | 5s |
| 2 (high) | Unread mail | Respond to mail (includes up to 3 bodies, truncated to 500 chars) | 5s |
| 3 (normal) | Current claim | Continue working on bead | 20s |
| 4 (normal) | Ready work | Pick up unblocked bead | 20s |
| 5 (idle) | Nothing pending | Skip — do not launch agent, re-poll after idle wait | 30s |

The idle case never launches the agent. The dispatcher already checked and found nothing — paying for a Claude session to rediscover that is waste.

### Prompt composition

Each cycle composes a prompt from layers:

```
Primary mission:
  [base prompt — from CLI arg or config, persistent across cycles]

Current cycle:
  [dispatch instruction — what to work on or respond to]

  [suffix — work or comms operating procedures from config]
```

- **Base prompt**: persistent standing directive (e.g., "focus on test coverage"). Optional. From CLI arg or `base_prompt` in config.
- **Cycle prompt**: from dispatch — describes the specific work or comms for this cycle.
- **Suffix**: appended based on context. `work_prompt_suffix` for bead work, `comms_prompt_suffix` for chat/mail. Configurable in `run.json`.

If dispatch skips (nothing to do) but the human typed a prompt, the skip is overridden and the agent runs with that prompt.

### Session management

- **Continue session**: when staying on the same task (priorities 1-3, same context)
- **Fresh session**: when picking up new work (priority 4) or switching tasks
- The wrapper tracks session_id from the agent's structured output
- `--resume` maintains session context when continuing after `/stop`

## Terminal UX

Built on bubbletea (alternate screen buffer with viewport + text input). The terminal has three zones: scrollable output viewport, status bar, and input line.

### Display

Agent activity is shown as a formatted stream with color coding:
- **Blue bold**: run headers (run number, timestamp, prompt)
- **Yellow**: tool calls (name + summarized arguments)
- **Cyan**: tool results (truncated output)
- **Green bold**: completion (duration, cost)
- **Grey**: system info, hints

Prompt/policy echo from Claude's startup is detected and suppressed to reduce noise.

### During a run (agent is active)

| Command | Effect |
|---------|--------|
| `/stop` | Cancel current run, pause. Agent can be resumed. |
| `/wait` | Let current run finish, then pause before next cycle |
| `/quit` | Cancel current run and exit the loop |
| `/resume` | Resume from a pause |
| Any text + Enter | Queued as a one-run mission override for the next cycle |

### During idle (between runs)

Status bar shows countdown ("next run in Ns" or "waiting for work in Ns"). Human can:
- Type a prompt + Enter → one-run override, forces a run even if dispatch would skip
- `/stop` → pause
- `/quit` → exit
- Let the countdown expire → re-poll dispatch

## Configuration

`~/.config/beadhub/run.json` — personal defaults. CLI flags override config. All fields optional.

```json
{
  "base_prompt": "You are a backend developer focused on API stability.",
  "work_prompt_suffix": "Before closing the bead, run a self-review or code-reviewer pass on your changes.",
  "comms_prompt_suffix": "",
  "wait_seconds": 20,
  "idle_wait_seconds": 30
}
```

Create interactively with `bdh :run --init`.

### CLI flags

| Flag | Description |
|------|-------------|
| `--wait N` | Override `wait_seconds` |
| `--idle-wait N` | Override `idle_wait_seconds` |
| `--session` | Resume same provider session across runs |
| `--max-runs N` | Stop after N runs (0 = infinite) |
| `--dir PATH` | Working directory for agent process |
| `--allowed-tools LIST` | Provider-specific tool allowlist |
| `--model NAME` | Provider-specific model override |
| `--provider NAME` | Agent provider (default: claude) |
| `--ignore-beads` | Only wake for comms, ignore claims and ready tasks |
| `--init` | Create/update config file interactively |

## Code review

The `work_prompt_suffix` config handles review reminders. The default suffix reminds the agent to run a self-review before closing a bead. Teams can customize or remove this via config.

Cross-agent review is a coordination decision made by the coordinator via policy, not enforced by the wrapper.

## Provider abstraction

The wrapper is not tied to Claude Code. Different AI coding CLIs have different invocation patterns and output formats. The wrapper abstracts this behind a provider interface:

```
Provider
  ├── BuildCommand(prompt, options) → command + args
  ├── ParseOutput(line) → structured event (tool_call, result, text, done)
  ├── SessionID(done_event) → string (for continuation)
  └── Capabilities() → what this provider supports
      (session resume, continue, streaming, allowed-tools, etc.)
```

### Claude Code provider

- Invocation: `claude -p <prompt> --output-format stream-json --verbose --dangerously-skip-permissions`
- Session resume: `--resume <session_id>`
- Session continue: `--continue`
- Tool scoping: `--allowedTools <list>`
- Output: JSON lines with event types (stream_event, assistant, tool_result, result, system)

### Codex provider (planned)

- Invocation: TBD (depends on Codex CLI interface)
- Same structured event model, different parsing

Adding a provider means implementing the interface above. The dispatch logic, terminal UX, and bdh integration are shared.

## Open questions

- **Presence keepalive**: should the wrapper ping beadhub between runs to maintain presence?
- **Stuck detection**: if the same prompt runs N times with no progress, should the wrapper escalate?
- **SSE vs polling**: beadhub has an SSE stream. The wrapper could subscribe and react to events in real-time instead of polling between runs.
