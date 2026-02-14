# beadhub — Source of Truth

## What This Is

Open-source coordination server for AI coding agents. Embeds aweb for agent primitives (identity, mail, chat, locks, presence), adds beads sync, workspaces, policies, claims, escalations, and subscriptions.

## Stack

- **Language**: Python 3.12+
- **Framework**: FastAPI
- **Database**: PostgreSQL via pgdbm (schema isolation)
- **Cache**: Redis (presence, locks, pub/sub)
- **Package manager**: Always use `uv`

## Ecosystem Role

Core server. API consumed by `bdh` (Go CLI). Mounted inside beadhub-cloud at `/v1` for the managed SaaS deployment. Can also run standalone for self-hosted setups.

## Key Architecture

- `src/beadhub/routes/` — FastAPI endpoints
- `src/beadhub/defaults/` — Default policy content (roles, invariants) loaded at startup
- Schema isolation via pgdbm: `aweb`, `server`, `beads` schemas coexist in the same Postgres database
- Workspace model ties agents to git repos — each workspace has an alias, role, and human name
- Policy system: project-level invariants + role playbooks that guide agent behavior

## Development

```bash
uv run beadhub          # Run server
uv run pytest           # Run tests
```

## Release

PyPI package + Docker image, triggered by git tags (`vX.Y.Z`).

## Dependencies

- **aweb** (Python package) — embedded for identity, mail, chat, locks, presence
