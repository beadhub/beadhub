# Self-hosting aweb

This package is intended to be genuinely usable on its own.

Minimum requirements:

- PostgreSQL
- Redis
- Python 3.12+ if running directly with `uv`

## Run with uv

```bash
cd server
uv sync
export AWEB_DATABASE_URL=postgresql://aweb:password@localhost:5432/aweb
export AWEB_REDIS_URL=redis://localhost:6379/0
uv run aweb serve
```

The server listens on `http://localhost:8000` by default and exposes:

- the HTTP API
- SSE/event routes
- the MCP endpoint at `/mcp/`

## Run with Docker Compose

```bash
cd server
cp .env.example .env
docker compose up --build
```

This starts:

- `postgres`
- `redis`
- `aweb`

## Important environment variables

- `AWEB_DATABASE_URL`
- `AWEB_REDIS_URL`
- `AWEB_CUSTODY_KEY`
- `AWEB_MANAGED_DOMAIN`

`AWEB_CUSTODY_KEY` is optional, but without it custodial signing is disabled.

## Identity system

The stable identity system is part of OSS `aweb` under:

```text
src/aweb/awid/
```

That includes:

- `did:key` and `did:aw`
- signing and verification
- audit-log verification helpers
- continuity/replacement metadata helpers
