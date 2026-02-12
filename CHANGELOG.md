# Changelog

All notable changes to this project are documented in this file.

This project follows a pragmatic, OSS-friendly changelog format (similar to Keep a Changelog), but versioning is currently evolving.

## Unreleased

## 0.2.4 — 2026-02-11

### Fixed
- Reverted in-place edit of 001_initial.sql; visibility column now added via additive 002 migration (safe for existing databases)

## 0.2.3 — 2026-02-11

### Fixed
- Actor-binding check no longer blocks Cloud proxy mode (project-scoped keys don't need workspace-level binding)
- Extracted `enforce_actor_binding()` helper to eliminate 10 inline copies

## 0.2.2 — 2026-02-11

### Changed
- README: agent-first onboarding with "paste to your agent" setup blocks for managed and self-hosted
- Added project visibility column to initial migration

## 0.2.1 — 2026-02-10

### Fixed
- Dashboard no longer gates policies on workspace identity
- Onboarding flow documentation and isolated port usage for start/stop

## 0.2.0 — 2026-02-08

### Added
- Claim enforcement: reject commands when bead already claimed by another workspace
- Workspace alias suggestions query aweb.agents for used aliases

### Changed
- Chat commands renamed: `chat send` → `chat send-and-wait` / `chat send-and-leave`, `chat hang-on` → `chat extend-wait`
- Dashboard palette updated to match design spec
- "Implementer" role renamed to "developer"
- Bumped aweb dependency to 0.1.3

### Fixed
- Race condition in claim enforcement
- Workspace focus fields populated when claiming beads
- Workspace identity validated against API key
- Peer cleanup of stale workspaces
- Beads API responses include created_at and updated_at

### Removed
- Dead Redis chat connection tracking code from events.py (now handled by aweb)

## 0.1.0 — 2026-01-06

Initial open-source release.

### Added
- FastAPI server with Redis + Postgres backing services
- Real-time dashboard (SSE) for status, workspaces, claims, escalations, issues, and policies
- Beads integration (client-push sync of `.beads/issues.jsonl`)
- Agent messaging + chat sessions
- `bdh` CLI wrapper for bead-level coordination (preflight approve/reject + sync)

### Security
- Project-scoped tenant isolation model (`project_id`)
- CLI safety checks for repo identity / destructive actions

