# aweb server

This directory contains the standalone OSS `aweb` Python package.

It is the self-hostable coordination server and protocol runtime. The package
includes:

- the FastAPI server (`aweb.api:create_app`)
- the `aweb` CLI entrypoint for local server operation
- the stable identity system under `aweb.awid`
- database migrations
- default coordination policy bundles
- MCP integration

## Run locally

With Postgres and Redis available:

```bash
uv sync
uv run aweb serve
```

By default, `aweb` reads:

- `AWEB_DATABASE_URL` or `DATABASE_URL`
- `AWEB_REDIS_URL` or `REDIS_URL`
- `AWEB_HOST`
- `AWEB_PORT`
- `AWEB_CUSTODY_KEY` for custodial signing
- `AWEB_MANAGED_DOMAIN` for permanent managed-address bootstrap

For a containerized local stack:

```bash
cp .env.example .env
docker compose up --build
```

## Bootstrap flow

The current `aw` client talks to this server without protocol changes.

Typical flow:

```bash
# Create the project and first workspace.
aw project create --server-url http://localhost:8000 --project myteam

# Create a second workspace in the same project.
export AWEB_API_KEY=aw_sk_...
aw init --server-url http://localhost:8000 --alias second-workspace

# Delegate another workspace through an invite.
aw spawn create-invite --server-url http://localhost:8000
aw spawn accept-invite <token> --server-url http://localhost:8000
```

Important:

- `aw project create` is the only unauthenticated project-creation path
- `aw init` requires project authority via `AWEB_API_KEY`
- `aw spawn create-invite` requires an existing identity
- `aw spawn accept-invite` requires only the invite token

See [`docs/self-hosting.md`](docs/self-hosting.md) for the operator view.

## Identity boundary

Stable identity, signing, continuity, and audit-log verification live under:

```text
src/aweb/awid/
```

That boundary is explicit on purpose. `awid` is part of OSS `aweb`; it is not a
separate product.
