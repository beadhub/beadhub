# beadhub — Source of Truth

Open-source coordination server for AI coding agents. Agents register workspaces, claim work, exchange messages, lock files, follow policies, and manage tasks — all scoped per project.

## Ecosystem

beadhub is the server in a three-part system:

| Component | What it is | Repo |
|-----------|-----------|------|
| **aweb** | Python library — agent coordination protocol. Identity, API keys, mail, chat, file locks, presence. | [awebai/aweb](https://github.com/awebai/aweb) |
| **bdh** | Go CLI — the client agents use. Coordination commands (`:status`, `:policy`, `:aweb mail/chat`) plus optional `bd` (beads) wrapping for git-native issue tracking. | [beadhub/bdh](https://github.com/beadhub/bdh) |
| **beadhub** | Python server — this repo. Embeds aweb, adds workspaces, tasks, claims, policies, sync. | [beadhub/beadhub](https://github.com/beadhub/beadhub) |
| **beadhub-cloud** | Managed SaaS wrapper. Mounts beadhub at `/api/v1`, adds user accounts, billing, proxy auth. Not open-source. | — |

### Data flow

```
Agent runs bdh commands
    │
    ├─ Task API (create, update, close) ─────────────────────────────────────┐
    ├─ :aweb commands (mail, chat, locks) ───────────────────────────────────┤
    ├─ bd commands (beads mode) → local .beads/issues.jsonl                  │
    │                                                                        │
    └─ After beads mutations: bdh sync ──────────────────────────────────────┤
                                                                             │
                                                                             ▼
                                                                   beadhub server
                                                                   (embeds aweb)
                                                                        │
                                                        ┌───────────────┼───────────────┐
                                                        ▼               ▼               ▼
                                                   PostgreSQL        Redis         aweb mail/
                                                   (3 schemas)    (presence,       chat/locks/
                                                                   pub/sub)        tasks
```

Tasks can be managed natively via the aweb tasks API, or synced from the client's local beads database via `bdh sync`. In beads mode, the client is the authority for issues — it pushes state to the server. In native mode, the server is authoritative.

### aweb vs beadhub layering

**aweb** is the protocol layer: projects, agents, API keys, aliases, auth, async mail, persistent chat, file reservations (locks). It knows nothing about issues, policies, or workspaces.

**beadhub** is the domain layer built on top: workspaces (agent-repo bindings), tasks (native or synced from beads), claims (who's working on what), policies (project rules + role playbooks), escalations (human intervention), subscriptions (bead status notifications), presence.

beadhub embeds aweb as a library — aweb routers are mounted directly into the FastAPI app, and aweb tables live in the same Postgres database under the `aweb` schema. beadhub overrides aweb's `/v1/init` with an extended version that creates both an aweb agent and a beadhub workspace atomically.

## Stack

- **Python 3.12+**, FastAPI, uvicorn
- **PostgreSQL** via [pgdbm](https://github.com/juanre/pgdbm) — async Postgres library with schema-isolated managers, template-based table naming (`{{tables.workspaces}}` → `server.workspaces`), and migration support. One connection pool shared across all schemas.
- **Redis** — presence cache, file locks, pub/sub for real-time SSE events. Ephemeral; Postgres is authoritative for all persistent data.
- **Package manager**: always `uv` (never pip)

## Identity & Bootstrap

### The identity stack

Three files on the client side establish who an agent is:

| File | Location | Contains | Secret? |
|------|----------|----------|---------|
| `.beadhub` | Worktree root | `workspace_id`, `alias`, `role`, `human_name`, `beadhub_url`, `repo_origin`, `canonical_origin` | No |
| `.aw/context` | Worktree root | Account name — pointer into the credential store | No |
| `~/.config/aw/config.yaml` | Home directory | API keys (`aw_sk_...`) per server, shared across worktrees | Yes |

`bdh` reads all three to build each request: `.beadhub` for workspace metadata, `.aw/context` to select the account, `~/.config/aw/config.yaml` for the bearer token.

One worktree = one agent identity. Running `bdh` from a different worktree means acting as a different agent.

### Bootstrap flow (`POST /v1/init`)

When an agent joins a project (via `bdh :init`):

1. **aweb layer**: ensure project exists → create agent (with alias) → mint API key `aw_sk_...` (stored as SHA-256 hash, plaintext returned once)
2. **beadhub layer**: ensure repo exists → create workspace with `workspace_id == agent_id` → store role, alias, human_name, repo binding
3. **Client**: saves API key to `~/.config/aw/config.yaml`, creates `.aw/context` and `.beadhub`

This is the only time the plaintext API key is returned. All subsequent requests use it as a bearer token.

## Core Concepts

### Project
Tenant boundary. All data is scoped by `project_id`. A project has a slug (globally unique among active projects), name, visibility, and an active policy. In multi-tenant (Cloud) mode, projects also have a `tenant_id`.

### Workspace
An agent's working context within a project, bound to a specific repo. Has `workspace_id`, `alias`, `role`, `human_name`. In v1, `workspace_id == agent_id` (aweb identity). Immutable links: workspace→project and workspace→repo never change after creation. Soft-deleted via `deleted_at`.

### Repo
A git repository tracked by beadhub, identified by `canonical_origin` (e.g., `github.com/org/repo`). Unique per project. Soft-deleted.

### Task / Bead
A unit of work tracked by the server. Tasks can originate from two sources:

- **Native tasks** (aweb): created and managed via the `/v1/tasks` API. The server is authoritative. Status changes trigger claim lifecycle hooks automatically.
- **Synced beads**: issues pushed from the client's `.beads/issues.jsonl` file via `POST /v1/bdh/sync`. The client is the authority — sync is a client-push model.

Both sources are unified in the claims and status display — a claimed task looks the same regardless of origin.

### Claim
Who's working on which task. A workspace claims a task when it moves to `in_progress` (native) or during sync (beads). Multiple agents can claim the same task (coordinated work). Claims track `apex_bead_id` for molecule (parent task) context. The server uses claims for pre-flight conflict detection: if an agent tries to work on a task another agent has claimed, `bdh` warns or blocks.

### Policy
Project-scoped, versioned bundle of invariants (rules for all agents) and role playbooks (role-specific guidance). Stored as JSONB. Defaults loaded from markdown files in `src/beadhub/defaults/` at startup. Supports optimistic concurrency: `base_policy_id` in create request triggers a 409 if the active policy changed since the caller last read it.

### Escalation
A request for human intervention. An agent describes a situation, provides options, and waits for a response. Status lifecycle: pending → responded | expired.

### Subscription
An agent subscribes to status changes on specific beads. When a bead's status changes during sync, the notification outbox queues a mail to each subscriber.

## Authentication

Two modes, selected automatically based on request headers:

### Bearer Mode (standalone / direct)
Client sends `Authorization: Bearer aw_sk_...`. The token is hashed (SHA-256) and looked up in the aweb `api_keys` table. Extracts `project_id`, `agent_id`, and `api_key_id`. Actor binding is enforced: the `agent_id` in the token must match any `workspace_id` claimed in the request body.

### Proxy Mode (beadhub-cloud)
Cloud wrapper verifies the external user's identity, then injects signed headers: `X-BH-Auth` (HMAC-SHA256 signature), `X-Project-ID`, `X-User-ID` or `X-API-Key`, `X-Aweb-Actor-ID`. Requires `BEADHUB_INTERNAL_AUTH_SECRET` env var. Principal types: `u` (user), `k` (API key), `p` (public reader — read-only, PII redacted).

### Key auth functions
- `get_project_from_auth(request, db)` → project_id (for read-only endpoints)
- `get_identity_from_auth(request, db)` → AuthIdentity (for write endpoints)
- `enforce_actor_binding(identity, workspace_id)` → 403 if mismatch in bearer mode
- `is_public_reader(request)` → True if signed proxy with principal_type="p"

## Database Architecture

Three [pgdbm](https://github.com/juanre/pgdbm) schemas share one Postgres database with a single connection pool:

### `aweb` schema (managed by aweb library)
Projects, agents, API keys, messages, chat sessions, chat messages, reservations, tasks. Migrations live in the aweb package.

### `server` schema (beadhub's own)
| Table | Purpose |
|-------|---------|
| `projects` | Project root. Has `active_policy_id` FK, `visibility`, `tenant_id` |
| `repos` | Git repos. Unique `canonical_origin` per project |
| `workspaces` | Agent instances. Alias unique per project (partial index on non-deleted) |
| `bead_claims` | Active work claims. FK to workspace and project |
| `escalations` | Human escalation requests with response lifecycle |
| `subscriptions` | Bead status change notification subscriptions |
| `notification_outbox` | Outbox pattern for reliable notification delivery |
| `audit_log` | Event trail (sync events, policy changes, etc.) |
| `project_policies` | Versioned policy bundles (JSONB). Unique (project_id, version) |

### `beads` schema (for beads integration — not used in native task mode)
| Table | Purpose |
|-------|---------|
| `beads_issues` | Issues synced from client `.beads/issues.jsonl`. Cross-repo `blocked_by` as JSONB. GIN trigram indexes for search |

### pgdbm patterns
All queries use template syntax: `{{tables.workspaces}}` resolves to `server.workspaces`. Access a schema's manager via `db_infra.get_manager("server")`. Migrations live in `src/beadhub/migrations/{schema}/`. The aweb schema migrations are in the aweb package itself.

### Key database patterns
- **Project scoping**: every query filters by `project_id`
- **Soft-delete**: repos and workspaces use `deleted_at` timestamps, never hard-deleted
- **Immutable links**: workspace→project, workspace→repo, repo→project enforced by trigger
- **Atomic versioning**: policy version numbers allocated under `FOR UPDATE` row lock
- **Outbox pattern**: notifications written to `notification_outbox`, processed asynchronously

## API Surface

### aweb protocol endpoints (mounted from aweb library)
`/v1/auth/*`, `/v1/chat/*`, `/v1/messages/*`, `/v1/projects/*`, `/v1/reservations/*`, `/v1/tasks/*`

### beadhub endpoints

| Route file | Prefix | What it does |
|------------|--------|-------------|
| `init.py` | `POST /v1/init` | Bootstrap: create aweb agent + beadhub workspace in one call |
| `workspaces.py` | `/v1/workspaces` | Register, list, get, patch, soft-delete workspaces |
| `repos.py` | `/v1/repos` | Register, list, delete repos |
| `agents.py` | `/v1/agents` | Agent presence list, alias prefix suggestions |
| `beads.py` | `/v1/beads` | Issue upload (JSONL), list, get, ready (unblocked) |
| `bdh.py` | `/v1/bdh` | CLI sync (issues + claims + notifications), command pre-flight |
| `claims.py` | `/v1/claims` | List active bead claims |
| `policies.py` | `/v1/policies` | CRUD policy versions, activate, reset to defaults, history |
| `escalations.py` | `/v1/escalations` | Create, list, get, respond to escalations |
| `subscriptions.py` | `/v1/subscriptions` | Subscribe/unsubscribe to bead status changes |
| `status.py` | `/v1/status` | Workspace status snapshot + SSE stream |

### The sync endpoint (`POST /v1/bdh/sync`)
Used by the beads integration. Called by `bdh sync`. Accepts full (`issues_jsonl`) or incremental (`changed_issues` + `deleted_ids`) payloads. Upserts issues, updates claims, processes notification outbox, and returns sync stats. In native task mode, task mutations trigger claim lifecycle hooks directly via `mutation_hooks.py` instead of going through sync.

## Codebase Layout

```
src/beadhub/
  __init__.py          # Exports create_app(), main()
  api.py               # App factory, mounts aweb + beadhub routers, lifespan
  config.py            # Environment variable settings
  db.py                # DatabaseInfra: pgdbm pool + 3 schema managers
  auth.py              # Actor binding, workspace access verification
  aweb_introspection.py # Bearer + proxy auth → AuthIdentity
  internal_auth.py     # Proxy header parsing + HMAC verification
  presence.py          # Redis presence cache with secondary indexes
  notifications.py     # Outbox processing → aweb mail delivery
  events.py            # Redis pub/sub event bus for SSE
  claims.py            # Bead claim lifecycle (upsert, release, apex resolution)
  mutation_hooks.py    # Translates aweb task mutations into claim lifecycle + SSE events
  beads_sync.py        # Beads issue sync logic, validation, status change tracking
  defaults.py          # Load policy defaults from markdown files
  routes/              # FastAPI endpoint modules (see API Surface above)
  migrations/
    server/            # Server schema migrations
    beads/             # Beads schema migrations
  defaults/
    invariants/        # Default policy invariants (numbered markdown files)
    roles/             # Default role playbooks (markdown files)
```

## App Startup

`create_app()` in `api.py` supports two modes:

- **Standalone**: no args → creates its own Postgres pool and Redis connection, runs migrations, manages lifecycle.
- **Library**: pass `db_infra` and `redis` → uses externally managed connections. Used by beadhub-cloud to embed beadhub in a larger app.

aweb routers are mounted first (auth, chat, messages, projects, reservations), then beadhub's own routers.

## Test Infrastructure

Tests use pgdbm's `AsyncTestDatabase` for isolated test databases. Key fixtures in `tests/conftest.py`:

- `db_infra` — fresh DatabaseInfra with all migrations applied
- `test_db_with_schema` — bare pgdbm manager for low-level schema tests
- `beadhub_server` — full server subprocess on port 18765. Integration tests use `httpx` against this.
- `init_workspace()` — factory that calls `/v1/init` + `/v1/workspaces/register` and returns `(project_id, api_key)`
- Redis tests use database 15 (`redis://localhost:6379/15`)

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BEADHUB_DATABASE_URL` or `DATABASE_URL` | (required) | Postgres connection |
| `BEADHUB_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `BEADHUB_HOST` | `0.0.0.0` | Server bind address |
| `BEADHUB_PORT` | `8000` | Server port |
| `BEADHUB_LOG_LEVEL` | `info` | Log level |
| `BEADHUB_PRESENCE_TTL_SECONDS` | `1800` | Presence cache TTL |
| `BEADHUB_INTERNAL_AUTH_SECRET` | (none) | Enables proxy auth when set |
