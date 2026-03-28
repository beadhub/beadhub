# Agent Runtime — Foundational Design Note

**Status (2026-03-09):** Foundational Source of Truth for what `aw run` is becoming.
This document is architectural and directional. It defines the intended runtime
boundary between `aw`, `atext`, and `aweb`, even where the implementation is
still incomplete.

---

## 1. Purpose

`aw run` is the general agent runtime.

It is not a bead runner, not a server, and not a provider-specific shell
script. It is the reusable local runtime that:

- runs a provider loop
- owns local input/output and local machine capabilities
- consumes remote wake/control signals delivered through `atext`
- exposes a stable integration surface for higher-level coordination products

This note exists so future work does not drift back into ad hoc layering where
runtime behavior is reimplemented in product wrappers or mixed into transport.

---

## 2. Layer Boundary

### `aw`

`aw` owns the **general agent runtime**:

- provider adapters and session continuity
- local run loop and prompt/control handling
- screen/input controller
- service supervision
- run configuration
- wake stream consumption
- capability execution on the local machine

`aw run` is the canonical CLI surface for this runtime.

### `atext`

`atext` owns **transport, identity, and delivery**:

- authenticated transport
- agent identity and addressing
- event delivery
- control delivery
- presence and state distribution
- durable audit/event storage as needed by the networked system

`atext` should not own provider-specific run loops or local machine tool wiring.

### `aweb`

`aweb` owns **coordination rules and task-aware dispatch**:

- ready-work / claim / mail prioritization
- task-aware autofeed and dispatch rules
- prompts and behaviors that depend on coordination semantics
- product logic that is specifically about hosted and managed coordination

`aweb` should consume the `aw` runtime, not reimplement it.

---

## 3. Runtime Model

The intended runtime stack is:

1. `atext` delivers events and control inputs to the agent.
2. `aw run` maps those inputs into a local runtime loop.
3. The runtime loop decides when to run a provider, pause, resume, wait, or
   invoke capabilities.
4. Provider execution and capability execution happen on the local machine that
   owns the relevant access.
5. Higher-level coordination products influence the runtime by providing
   dispatch rules, not by replacing the runtime itself.

This means the runtime is **provider-agnostic** and **product-agnostic**.
Claude, Codex, and later providers are adapters inside the same loop.
Task-aware and non-task-aware products should sit above the same loop.

---

## 4. Control Plane

The runtime control plane is broader than “pause/resume”.

It carries four classes of intent:

### Wake

A wake signal says: something happened that may justify another local cycle.

Examples:

- incoming mail
- incoming chat
- work available
- claim update / claim removed

Wake does not directly mutate the provider session. It tells the runtime to
reconsider whether to run.

### Control

A control signal says: change the runtime’s execution state.

Examples:

- pause
- resume
- interrupt
- stop after current cycle
- quit

Control affects the local loop state directly.

### Steer

A steer signal says: change what the next run should do.

Examples:

- queue a prompt override
- replace the current mission prompt
- request a follow-up run with new context

Steer is logically distinct from wake. Wake says “look again”; steer says
“look again with this direction”.

### Capability Invocation

A capability invocation says: ask the machine that owns a capability to execute
it as a structured operation.

Examples:

- fetch a repo branch
- read a local secret-backed resource
- perform an approval-gated deployment step

This is not the same thing as forwarding raw provider tool calls over the
network. It is a structured, named, rules-checked request.

---

## 5. Capability Model

The runtime should move toward **structured capability advertisement and
invocation**, not raw remote MCP tunneling.

### Principle

Capabilities are advertised as explicit named operations with schemas,
constraints, and rule hooks.

Examples:

- `git.fetch_branch`
- `build.run_tests`
- `deploy.preview`
- `messages.send_mail`

Each capability should define:

- stable name
- argument schema
- approval requirements
- audit fields
- locality/ownership constraints

### MCP Boundary

MCP remains local to the machine that owns access.

If a machine has local access to a filesystem, token, browser profile, or other
sensitive tool, the MCP server for that access should stay on that machine.
Remote systems should not receive raw MCP reach-through by default.

Instead, the owning machine should expose higher-level structured capabilities
over the control plane when remote invocation is needed.

This preserves:

- locality of trust
- approval boundaries
- auditability
- rules enforcement

---

## 6. First-Class Concerns

The runtime/control plane must treat the following as first-class concerns,
not afterthoughts:

### Presence and State

The system should be able to represent whether an agent/runtime is:

- connected
- idle
- running
- paused
- awaiting approval
- interrupted
- degraded / disconnected

Presence is not just UI sugar. Other agents and products use it to decide when
to wake, steer, or hand off work.

### Approvals

Approval is part of the runtime protocol, not just provider UX.

Some controls and capabilities require explicit approval before execution. That
approval should be modeled as a runtime/control-plane concept with clear state
transitions and audit records.

### Audit Trail

The system should preserve a durable record of:

- wake causes
- control signals
- steering inputs
- capability advertisements
- capability invocations
- approvals and denials
- resulting state transitions

Auditability is required both for debugging and for trust.

### Rules Enforcement

Coordination rules must be enforceable above raw provider output.

Examples:

- which capabilities may be invoked
- which invocations require approval
- which remote actors may steer a runtime
- which controls are allowed in a given state

Coordination rules belong at the runtime/control-plane boundary, not scattered
across provider adapters.

---

## 7. Boundary Rules

The following rules are normative for future work:

1. `aw run` is the reusable runtime. New general runtime behavior should land in
   `aw`, not in product-specific wrappers.
2. `atext` is the network/control substrate. New event/control delivery behavior
   should land in `atext`/`aw` transport layers, not in higher-level products.
3. `aweb` may decide **when** and **why** to run, but it should not own the
   generic mechanics of running.
4. Remote capability use should prefer structured capability invocation over raw
   remote MCP tunneling.
5. MCP servers remain local to the machine that owns the underlying access.
6. Presence, approvals, audit trail, and rules enforcement are design inputs
   for every control-plane change.

---

## 8. Current Direction in `aw`

The current `aw` codebase already reflects the beginning of this split:

- root transport for event streaming
- reusable `run` package for provider/loop logic
- reusable `run` package config/init, services, and screen primitives
- `aw run` command wired to the extracted runtime

Remaining work is still needed, including control POST helpers and richer
control/capability surfaces, but those should extend this architecture rather
than redefine it.

---

## 9. Non-Goals

This design note does not require:

- `atext` to understand provider-specific command lines
- every wrapper pattern to disappear immediately
- raw remote execution of arbitrary local MCP servers
- every current runtime concern to be immediately networked

It does require that future networking, capability, and dispatch work preserve
the runtime boundary defined above.
