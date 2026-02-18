# Contributing

Thanks for helping improve BeadHub.

## Development setup

Prereqs:
- Python 3.12+
- `uv`
- PostgreSQL and Redis (via brew or Docker)
- Node.js + `pnpm` (only if working on the frontend)

Clone and set up:
```bash
git clone https://github.com/beadhub/beadhub.git
cd beadhub
uv sync
pnpm -C frontend install   # skip if backend-only
make hooks-install
```

## Run locally

The easiest way to run locally (uses local postgres/redis via brew):
```bash
make dev-setup      # One-time: starts postgres/redis, creates database
make dev-backend    # Run backend on port 8000
make dev-frontend   # Run frontend on port 5173 (separate terminal)
```

Or use Docker for everything:
```bash
make docker         # Runs full stack on port 9000
```

## Code quality

**All linting happens locally via pre-push hooks.** CI only verifies builds.

Install the hooks (required):
```bash
make hooks-install
```

The pre-push hook runs:
- Python: `ruff`, `black`, `isort`, `mypy`
- Frontend: `eslint`

To run checks manually:
```bash
make check          # Run all checks
make check-python   # Python lint + typecheck
make check-frontend # Frontend lint + build
make fmt-python     # Auto-format Python
```

Run tests:
```bash
uv run pytest           # Python tests
```

## Pull requests

- Keep PRs focused and small when possible.
- Add tests for behavior changes.
- Update docs when you change UX or external interfaces.
- Pre-push hooks must pass before pushing.

## Coordination with BeadHub

BeadHub coordinates work across contributors — claim tasks, communicate with the team, and avoid conflicts. The dashboard is at [app.beadhub.ai/juanre/beadhub](https://app.beadhub.ai/juanre/beadhub).

### Register

Install `bd` and `bdh` if you don't have them:

```bash
curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash
curl -fsSL https://raw.githubusercontent.com/beadhub/bdh/main/install.sh | bash
```

Get your API key from the [dashboard](https://app.beadhub.ai/juanre/beadhub), then from your fork's clone:

```bash
BEADHUB_API_KEY=<your-key> bdh :init --role contributor
```

The API key determines the project. See `bdh :policy` for full project rules after setup.

### Workflow

```bash
bdh ready                              # Find available work
bdh show <id>                          # Read the task description
bdh update <id> --status in_progress   # Claim it
# ... work, test, commit, push to your fork, open a PR ...
bdh :aweb mail send coordinator "PR #<number> ready for review"
bdh close <id>                         # After PR is merged
```

The coordinator is your primary point of contact for questions, blockers, and reviews.
