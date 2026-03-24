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
uv run aweb serve
```

By default, `aweb` reads:

- `DATABASE_URL`
- `REDIS_URL`
- `AWEB_CUSTODY_KEY` for custodial signing

For a containerized local stack:

```bash
cp .env.example .env
docker compose up --build
```

## Identity boundary

Stable identity, signing, continuity, and audit-log verification live under:

```text
src/aweb/awid/
```

That boundary is explicit on purpose. `awid` is part of OSS `aweb`; it is not a
separate product.
