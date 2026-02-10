# Contributing

Thanks for helping improve BeadHub.

## Development setup

Prereqs:
- Python 3.12+
- `uv`
- Node.js + `pnpm` (for the frontend)
- PostgreSQL and Redis (via brew or Docker)

Clone and set up:
```bash
git clone https://github.com/beadhub/beadhub.git
cd beadhub
uv sync
pnpm -C frontend install
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
