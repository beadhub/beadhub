# Development Setup

This guide covers setting up BeadHub for local development.

## Prerequisites

- **Python 3.12+**
- **uv** (Python package manager): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Redis** (local; optional via Docker)
- **PostgreSQL** (local; optional via Docker)
- **Docker + Docker Compose** (optional; convenient for running Redis/Postgres)

## Multi-repo layout (post-extraction)

Local development typically uses sibling checkouts:

```
beadhub-all/
  beadhub/      # this repo (beads + repo/workspace context; embeds aweb routes)
  aweb/         # aweb protocol server (standalone OSS implementation)
  aw/           # Go client + `aw` CLI (github.com/awebai/aw)
  bdh/          # BeadHub CLI (github.com/beadhub/bdh)
```

Key wiring:

- Python: `beadhub` depends on `aweb` and, for local development, uses a `uv` source override in `pyproject.toml` (`[tool.uv.sources] aweb = { path = "../aweb" }`).

## Quick Start

```bash
# Clone sibling repos (recommended for development)
mkdir -p beadhub-all && cd beadhub-all
git clone https://github.com/beadhub/beadhub.git
git clone https://github.com/awebai/aweb.git
git clone https://github.com/awebai/aw.git
git clone https://github.com/beadhub/bdh.git

cd beadhub

# Install dependencies
uv sync

# Run tests to verify setup
uv run pytest
```

## Project Setup

### 1. Install Dependencies

BeadHub uses [uv](https://github.com/astral-sh/uv) for dependency management:

```bash
# Install all dependencies (including dev dependencies)
uv sync

# Add a new dependency
uv add <package-name>

# Add a dev dependency
uv add --dev <package-name>
```

### 2. Start Infrastructure Services

You have three options:

**Option A: Local services (recommended for tests)**

BeadHub tests expect a locally reachable Postgres + Redis (no Docker-based test fixtures).

**Option B: Docker Compose (optional)**

Start just Redis and PostgreSQL, run the API locally:

```bash
# Set required password
export POSTGRES_PASSWORD=dev-password

# Start infrastructure only
docker compose up -d redis postgres

# Verify services are healthy
docker compose ps
```

**Option C: Full Stack via Docker**

Run everything including the API in Docker:

```bash
export POSTGRES_PASSWORD=dev-password
docker compose up -d

# Verify all services
curl http://localhost:8000/health
```

### 3. Environment Variables

Create a `.env` file or export these variables:

```bash
# Required for database connection
export POSTGRES_PASSWORD=dev-password

# These have sensible defaults but can be overridden:
export BEADHUB_DATABASE_URL=postgresql://beadhub:dev-password@localhost:5432/beadhub
export BEADHUB_REDIS_URL=redis://localhost:6379/0
export BEADHUB_HOST=0.0.0.0
export BEADHUB_PORT=8000

# Client API key (created by `bdh :init` / `POST /v1/init`):
# export BEADHUB_API_KEY=aw_sk_dev_key

# Optional: Path to beads issues file for sync
# export BEADS_JSONL_PATH=/path/to/project/.beads/issues.jsonl
```

## Running the API Server

### Development Mode (with auto-reload)

```bash
# Ensure Redis + Postgres are running (locally or via Docker), then:
export BEADHUB_REDIS_URL=redis://localhost:6379/0
export BEADHUB_DATABASE_URL=postgresql://beadhub:dev-password@localhost:5432/beadhub

# Run the API server with auto-reload
# NOTE: Use --factory flag because create_app is a factory function
uv run uvicorn beadhub.api:create_app --factory --reload --host 0.0.0.0 --port 8000
```

### Bootstrapping a project API key

After the server is running, initialize a workspace/project key from your repo:

```bash
bdh :init
```

This writes `.beadhub` (workspace metadata) and `.aw/context` (non-secret account pointer). The API key is stored in `~/.config/aw/config.yaml` (override with `AW_CONFIG_PATH`).

To authenticate the browser dashboard, run:

```bash
bdh :dashboard
```

This prints (and opens) a login URL that stores the key in your browser's localStorage. If you are running the Vite dev server on `http://localhost:5173`, set `BEADHUB_DASHBOARD_URL=http://localhost:5173/` (or pass `--dashboard-url`).

**If you have a local PostgreSQL running on port 5432** (common on macOS with Homebrew), use a different port for Docker:

```bash
# Start postgres on port 5433 to avoid conflict with local postgres
export POSTGRES_PASSWORD=dev-password
POSTGRES_PORT=5433 docker compose up -d redis postgres

# Update DATABASE_URL to use port 5433
export BEADHUB_REDIS_URL=redis://localhost:6379/0
export BEADHUB_DATABASE_URL=postgresql://beadhub:dev-password@localhost:5433/beadhub

# Run the API server
uv run uvicorn beadhub.api:create_app --factory --reload --host 0.0.0.0 --port 8000
```

### Using the CLI

```bash
# Run any CLI command (Python server CLI)
uv run beadhub --help

# Example (requires BEADHUB_API_KEY):
export BEADHUB_API_KEY=aw_sk_...
uv run beadhub escalations list
```

## Running Tests

### Prerequisites

Tests require:
- **PostgreSQL** running locally or in Docker (for database tests)
- **Redis** running locally or in Docker (for coordination tests)

The test suite uses pgdbm's test fixtures which create isolated test databases automatically.

### Configure Test Database

Set these environment variables (or use defaults):

```bash
# PostgreSQL connection for test database creation
export PGDBM_TEST_HOST=localhost
export PGDBM_TEST_PORT=5432
export PGDBM_TEST_USER=beadhub       # or postgres
export PGDBM_TEST_PASSWORD=dev-password
export PGDBM_TEST_DATABASE=postgres  # admin database for creating test DBs

# Redis for coordination tests (uses DB 15 by default to isolate from dev)
export BEADHUB_TEST_REDIS_URL=redis://localhost:6379/15
```

### Run Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_reservations.py

# Run a specific test
uv run pytest tests/test_reservations.py::test_acquire_lock_success

# Run tests matching a pattern
uv run pytest -k "reservation"

# Run with coverage
uv run pytest --cov=beadhub --cov-report=term-missing
```

To run the extracted sibling repos too:

```bash
# aweb (protocol server implementation)
cd ../aweb && uv run pytest

# aw (Go client + aw CLI)
cd ../aw && go test ./...

# bdh (BeadHub CLI)
cd ../bdh && go test ./...
```

### Test Structure

```
tests/
├── conftest.py              # Fixtures (redis_client, db_infra)
├── db_utils.py              # Database URL builder
├── helpers_app.py           # FastAPI test client helpers
├── test_reservations.py     # Lock/reservation tests
├── test_messages.py         # Messaging tests
├── test_escalations.py      # Escalation workflow tests
├── test_beads_sync.py       # Beads sync tests
├── test_beads_multi_repo.py # Multi-repo coordination tests
├── test_subscriptions.py    # Subscription/notification tests
└── ...
```

## Development Workflow

### 1. Check for Ready Work

```bash
bdh ready
```

### 2. Claim a Task

```bash
bdh update <bead-id> --status in_progress
```

> **Note:** Use `bdh` instead of `bd` to enable BeadHub coordination. If your claim is rejected because another agent has the bead, `bdh` will show you who has it and how to message them.

### 3. Make Changes

Edit code, run tests frequently:

```bash
# Run relevant tests
uv run pytest tests/test_<area>.py -v

# Scale fixture for team-status bounds
uv run pytest tests/test_workspaces_team.py::test_team_workspaces_bounded_at_scale

# Or run all tests
uv run pytest
```

### 4. Test Manually

```bash
# Start the dev server (with env vars set as described above)
uv run uvicorn beadhub.api:create_app --factory --reload

# In another terminal, test endpoints
curl http://localhost:8000/health
```

### 5. Complete the Task

```bash
bdh close <bead-id> --reason "Implemented feature X"
git add -A && git commit -m "feat: implement X"
```

## Pointing Agents at Local BeadHub

Use `bdh :init --beadhub-url http://localhost:8000` in your repo to connect an agent to a local server. See the self-hosted setup block in [README.md](../README.md#self-hosted) for the full flow.

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Test connection
docker compose exec postgres psql -U beadhub -d beadhub -c "SELECT 1"

# View logs
docker compose logs postgres
```

### Redis Connection Issues

```bash
# Check Redis is running
docker compose ps redis

# Test connection
docker compose exec redis redis-cli ping

# View logs
docker compose logs redis
```

### Test Failures

```bash
# Run with maximum verbosity
uv run pytest -vvs

# Check if services are available
docker compose ps

# Reset test databases (if stuck)
docker compose down -v && docker compose up -d redis postgres
```

### Port Conflicts

If ports 5432, 6379, or 8000 are in use:

```bash
# Use alternative ports
POSTGRES_PORT=5433 REDIS_PORT=6380 BEADHUB_PORT=8001 docker compose up -d

# Update environment accordingly
export BEADHUB_DATABASE_URL=postgresql://beadhub:dev-password@localhost:5433/beadhub
export BEADHUB_REDIS_URL=redis://localhost:6380/0
```

## Code Style

- Run Python checks with `make check-python`
- Auto-format Python with `make fmt-python`
- Install repo git hooks (bd JSONL flush + pre-push checks) with `make hooks-install`
- Format with `ruff format` / `black` / `isort` (or let your editor handle it)
- Follow existing patterns in the codebase
- Keep functions focused and testable
- Write tests for new functionality (TDD preferred)

See [docs/sot.md](sot.md) for architecture details.
