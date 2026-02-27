# Discord Bridge — Development Guide

> **Disclaimer**: This doc reflects the state as of 2026-02-26. Things may have changed since then — verify assumptions against the actual code and K8s manifests before relying on them.

## Overview

The discord-bridge mirrors BeadHub agent chat into Discord threads and relays human replies back. It runs as a single Bun service on K8s in the `beadhub` namespace.

```
BeadHub Chat → Redis pub/sub (events:*) → discord-bridge → Discord threads (via webhook)
Discord thread reply → discord-bridge → BeadHub Chat API → agents see it
```

## Architecture

- **Runtime**: Bun on `oven/bun:1-alpine`
- **Discord**: Uses discord.js with a channel webhook for posting (per-agent username/avatar override) and the bot client for reading replies
- **Redis**: PSUBSCRIBE `events:*` to catch `chat.message_sent` events from BeadHub
- **Session mapping**: Redis-backed bidirectional map (`session_id ↔ thread_id`)
- **Echo suppression**: Messages from the bridge's own alias (`dashboard-admin`) are skipped in the Redis listener to prevent duplicates
- **@mentions**: Guild members are fetched at startup to build a name→user ID map. Agent aliases get bold `**@alias**` formatting

## How to Test Locally (via K8s)

The bridge runs on the K8s cluster, not locally. To send test messages:

### 1. Port-forward the BeadHub API

```bash
kubectl --context homelab port-forward -n beadhub svc/beadhub-api 18000:80
```

### 2. Send a message using internal HMAC auth

BeadHub uses HMAC-signed headers for internal service auth. The bridge and other in-cluster services use this instead of API keys.

```python
import json, urllib.request, hashlib, hmac, uuid

# These come from K8s secrets — get them with:
#   kubectl --context homelab get secret -n beadhub beadhub-internal-auth -o jsonpath='{.data.secret}' | base64 -d
#   BEADHUB_PROJECT_ID is in the discord-bridge deployment manifest
PROJECT_ID = "9aa48935-607a-4b25-b7a7-11c8e4374b69"
SECRET = "<internal-auth-secret>"

# Build HMAC auth headers
pid = str(uuid.uuid4())
aid = str(uuid.uuid4())
msg = f"v2:{PROJECT_ID}:k:{pid}:{aid}"
sig = hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()

headers = {
    "Content-Type": "application/json",
    "X-BH-Auth": f"{msg}:{sig}",
    "X-Project-ID": PROJECT_ID,
    "X-API-Key": pid,
    "X-Aweb-Actor-ID": aid,
}

# Send a chat message as an agent
SESSION_ID = "<session-id>"  # Get from: GET /v1/chat/admin/sessions
WORKSPACE_ID = "<agent-workspace-id>"  # From the session participants list

data = json.dumps({
    "body": "Hello from the test script",
    "workspace_id": WORKSPACE_ID,
    "alias": "alice"
}).encode()

req = urllib.request.Request(
    f"http://localhost:18000/v1/chat/sessions/{SESSION_ID}/messages",
    data=data, method="POST", headers=headers
)
resp = urllib.request.urlopen(req)
print(resp.read().decode())
```

### 3. Useful API endpoints

All require the HMAC headers above.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/chat/admin/sessions` | List all chat sessions |
| GET | `/v1/chat/admin/sessions/{id}/messages?limit=50` | Get messages in a session |
| POST | `/v1/chat/admin/sessions/{id}/join` | Join a session (body: `{workspace_id, alias}`) |
| POST | `/v1/chat/sessions/{id}/messages` | Send a message (body: `{body, workspace_id, alias}`) |
| POST | `/v1/dashboard/identity` | Get/create bridge identity |

### 4. Known workspace IDs (current state)

| Alias | Workspace ID |
|-------|-------------|
| orchestrator | `1ea3da1d-83cb-4e29-8b04-60cafb7c15b9` |
| alice | `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` |
| dashboard-admin (bridge) | `c1e07fdd-3719-4a58-8642-f3d853488ea9` |

## Build & Deploy Cycle

No CI/CD pipeline is wired up for this yet. Manual process:

```bash
# 1. Make changes in discord-bridge/src/

# 2. Build and push (from discord-bridge/ directory)
docker buildx build --platform linux/arm64 -t ghcr.io/woody88/discord-bridge:main --push .

# 3. Restart the pod to pull the new image
kubectl --context homelab rollout restart deployment/discord-bridge -n beadhub
kubectl --context homelab rollout status deployment/discord-bridge -n beadhub

# 4. Check logs
kubectl --context homelab logs -n beadhub deployment/discord-bridge --tail=30
```

The image is `linux/arm64` because the cluster runs on a Raspberry Pi 5.

## Key Files

```
discord-bridge/
  src/
    index.ts              # Boot sequence: Redis, Discord, health server
    config.ts             # Env vars (all from K8s deployment manifest)
    types.ts              # Event/message interfaces
    redis-listener.ts     # PSUBSCRIBE events:*, dispatch chat events to Discord
    beadhub-client.ts     # HTTP client for BeadHub admin API (HMAC auth)
    discord-sender.ts     # Webhook posting, thread creation, @mention resolution
    discord-listener.ts   # Human replies in Discord → relay to BeadHub
    session-map.ts        # session_id ↔ thread_id mapping (Redis-backed)
  Dockerfile              # Multi-stage oven/bun:1-alpine
```

## K8s Manifest

Lives in the homelab-k8s repo (not this repo):

```
~/Code/DevOps/homelab-k8s/manifests/platform/beadhub/discord-bridge.yaml
```

Environment variables are set there. The Discord bot token comes from a K8s secret (`discord-bot-token`) managed by ExternalSecrets + Bitwarden SM.

## Discord Bot

- **Bot**: Claude#5299 (Bot ID: 1400735630366871572)
- **Guild**: 1400737043340070922
- **Required privileged intents**: Server Members (for @mention resolution), Message Content
- **Webhook**: Pre-configured on #agent-comms channel, URL in deployment env vars
- **Developer Portal**: https://discord.com/developers/applications

## Gotchas

- **HMAC auth**: The `X-API-Key` and `X-Aweb-Actor-ID` headers use random UUIDs per request — they're not real API keys, just part of the HMAC signature payload
- **Echo suppression**: The bridge identity alias is `dashboard-admin`. Messages from this alias are skipped in the Redis listener. If the identity name changes, the echo fix still works because it's passed dynamically from `getOrCreateBridgeIdentity()`
- **Event deduplication**: The same chat message fires events on each participant's Redis channel. The bridge deduplicates by `message_id` using a 60s TTL Set
- **Privileged intents**: `GuildMembers` intent must be enabled in the Discord Developer Portal or the pod will crash with "Used disallowed intents"
- **Port-forward**: When testing via `kubectl port-forward`, the connection drops after ~5 minutes of inactivity. Restart it if you get 401s or connection refused
