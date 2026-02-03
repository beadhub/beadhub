# Deployment Guide

BeadHub OSS is designed for **trusted networks** (local development, VPN, private LAN). This guide covers production deployment considerations.

## Quick Start (Development)

For local development, no special configuration is needed beyond starting the dependencies:

```bash
POSTGRES_PASSWORD=demo docker compose up -d
```

To bootstrap a project API key for CLI/dashboard access, run `bdh :init` in your repo/workspace (or call `POST /v1/init` directly).

To authenticate the dashboard in your browser, run:

```bash
bdh :dashboard --dashboard-url http://localhost:8000/
```

The dashboard stores the key in your browser's localStorage (it is not read from local files automatically).

## Production Deployment

### Security Checklist

Before exposing BeadHub beyond a trusted network:

- [ ] Set `POSTGRES_PASSWORD` to a strong, random value
- [ ] Configure TLS termination (HTTPS) via reverse proxy
- [ ] Restrict network access (firewall, VPC, private network)
- [ ] Enable Redis AUTH in production
- [ ] Use TLS for Redis connections (`rediss://`)

### Environment Variables

**Required:**

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Database password (required, no default) |

**Recommended for production:**

| Variable | Description |
|----------|-------------|
| `BEADHUB_LOG_JSON` | Set to `true` for structured logging |
| `BEADHUB_LOG_LEVEL` | Set to `WARNING` or `ERROR` in production |
| `SESSION_SECRET_KEY` | Secret used for session signing; may also be used for internal auth validation in embedded/proxy deployments if `BEADHUB_INTERNAL_AUTH_SECRET` is unset |
| `BEADHUB_INTERNAL_AUTH_SECRET` | (Embedded/proxy only) HMAC secret to validate `X-BH-Auth` internal context |

**Server configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADHUB_DATABASE_URL` | (required) | PostgreSQL connection URL |
| `BEADHUB_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `BEADHUB_HOST` | `0.0.0.0` | Host to bind |
| `BEADHUB_PORT` | `8000` | Port to bind |
| `BEADHUB_PRESENCE_TTL_SECONDS` | `1800` | Workspace offline timeout |

See `.env.example` for a complete template.

### API Key Authentication

BeadHub uses **project API keys**. Clients authenticate with:

```bash
# Example authenticated request (client-side key):
curl -H "Authorization: Bearer aw_sk_your-secret-key" \
  http://localhost:8000/v1/status
```

To obtain a key in a fresh deployment, use `bdh :init` (recommended) or call `POST /v1/init`.

### TLS Configuration

BeadHub doesn't handle TLS directly. Use a reverse proxy:

**Nginx example:**

```nginx
server {
    listen 443 ssl;
    server_name beadhub.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE requires special handling
    location /v1/status/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### Redis Security

Redis stores ephemeral state (presence, messages, pub/sub). In production:

1. **Network isolation**: Redis should not be publicly accessible
2. **Authentication**: Enable Redis AUTH
3. **TLS**: Use `rediss://` URLs for encrypted connections

```bash
# Redis with AUTH
BEADHUB_REDIS_URL=redis://:password@redis-host:6379/0

# Redis with TLS (managed services like AWS ElastiCache)
BEADHUB_REDIS_URL=rediss://:password@redis-host:6379/0
```

### PostgreSQL Security

1. **Strong password**: Use a randomly generated password
2. **Network isolation**: Database should not be publicly accessible
3. **TLS**: Enable SSL connections for production

```bash
# PostgreSQL with SSL
BEADHUB_DATABASE_URL=postgresql://user:password@host:5432/beadhub?sslmode=require
```

## Docker Compose Production

For production deployments, create a `docker-compose.prod.yml`:

```yaml
services:
  api:
    image: ghcr.io/beadhub/beadhub:latest
    environment:
      - BEADHUB_DATABASE_URL=postgresql://beadhub:${POSTGRES_PASSWORD}@postgres:5432/beadhub
      - BEADHUB_REDIS_URL=redis://redis:6379/0
      - BEADHUB_LOG_JSON=true
      - BEADHUB_LOG_LEVEL=WARNING
    ports:
      - "127.0.0.1:8000:8000"  # Bind to localhost only
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16
    environment:
      - POSTGRES_USER=beadhub
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=beadhub
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

Run with:

```bash
POSTGRES_PASSWORD=secure-random-password \
docker compose -f docker-compose.prod.yml up -d
```

## Trust Model

BeadHub OSS assumes a **trusted network**:

- Agents authenticate with a **project API key** (Bearer token)
- The OSS server is intended to run behind network controls (VPN, firewall rules, private network)
- There is no multi-user RBAC model in OSS; the project key is the primary boundary

This works well for:
- Local development
- Team VPN
- Private networks (e.g., VPC)

For untrusted networks, add network-level access control (VPN, firewall rules, private network).

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

Returns:
```json
{
  "status": "ok",
  "checks": {
    "redis": "ok",
    "database": "ok"
  }
}
```

### Logs

With `BEADHUB_LOG_JSON=true`, logs are structured JSON for easy parsing:

```json
{"timestamp": "2025-01-10T12:00:00Z", "level": "INFO", "message": "Request completed", "path": "/v1/status", "duration_ms": 15}
```

### API Documentation

The server provides auto-generated OpenAPI docs:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
