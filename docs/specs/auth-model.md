# BeadHub Auth Model (OSS + Proxy Embedding)

This spec describes the intended authentication and project-scoping model for BeadHub **OSS** deployments and for deployments where the OSS server is embedded behind a trusted gateway (reverse proxy / wrapper) that injects a signed internal auth context.

The model is designed for **private/protected deployments**, with a clear public-client contract and a separate proxy-injected internal context for embedded deployments.

## Design Summary

- Public clients authenticate with `Authorization: Bearer <project_api_key>` (`aw_sk_...`).
- Project scope is derived server-side from the Bearer token (OSS) or from a trusted internal context (proxy embedding).
- Public clients do not send project scoping headers (e.g., `X-Project-ID`).
- Dashboard SSE uses a header-capable streaming approach (not `EventSource`).

## Goals

- **Single public-client auth scheme**: all public clients authenticate with:
  - `Authorization: Bearer <project_api_key>`
  - where `<project_api_key>` is an `aw_sk_...` (secret) key issued by the system.
- **Server derives project from auth**: project scope is derived server-side from the Bearer token (OSS) or from a trusted internal context (proxy embedding).
- **One project per key**: a project API key authorizes exactly one project; public clients never “pick” a project independently.
- **No server-side auth toggle**: server behavior must not depend on a server-side `BEADHUB_API_KEY` env var.
- **No public `X-Project-ID`**: public clients (CLI and browser) never send `X-Project-ID`.
- **Embedding preserved**: the gateway terminates public auth (API key/JWT) and injects a trusted internal auth context to the OSS app.

## Non-goals

- Exposing the OSS server to the public internet.
- Implementing a full multi-user RBAC model for OSS.
- Requiring end users to run any CI workflows locally.

## Terminology

- **Project API key**: the credential a human/agent uses to access a project on a server (`aw_sk_...`).
- **Internal auth context**: a trusted set of headers injected by a gateway into the OSS server (not settable by public clients).

## Environment Variable Meanings

| Variable | Where set | Meaning in this model |
|----------|-----------|-----------------------|
| `BEADHUB_API_KEY` | **Client** (bdh, dashboard, scripts) | Project API key (Bearer token). Not used by the server as an auth toggle. |
| `BEADHUB_INTERNAL_AUTH_SECRET` | **Server** (embedded mode only) | HMAC secret used to validate gateway-injected internal auth context (`X-BH-Auth`). |
| `SESSION_SECRET_KEY` | **Server** | Existing server secret. Some deployments may reuse it to sign `X-BH-Auth` if `BEADHUB_INTERNAL_AUTH_SECRET` is unset. |

## Public Client Contract (bdh, dashboard, scripts)

### Auth

- Clients send `Authorization: Bearer <project_api_key>` on **all** API requests to a BeadHub server (standalone or embedded).
- The key is provided via environment variable `BEADHUB_API_KEY` (client-side meaning only).

### Local configuration

- API keys are stored globally in `~/.config/aw/config.yaml` (override path with `AW_CONFIG_PATH`).
- Each worktree has `.aw/context` (non-secret) selecting which account to use.
- `.beadhub` contains **workspace identity only**; it must not contain secrets and must not contain `project_id`.
- Escape hatch: scripts/CI can still set `BEADHUB_URL` + `BEADHUB_API_KEY` directly.

### SSE (dashboard)

- Browser clients must be able to authenticate SSE.
- Since `EventSource` cannot send auth headers, SSE must use a `fetch()` streaming implementation (or another approach that supports headers).

## OSS Server Contract

### Auth enforcement

- All project-scoped endpoints must require a valid **project context**.
- The OSS server does not read `BEADHUB_API_KEY` from the server environment for auth decisions; project keys live in the DB (`api_keys`).
- The OSS server must not require `X-API-Key`.
- The OSS server should not require any *server-side* `BEADHUB_API_KEY` at all; allowed keys live in the DB (`api_keys`).

### Project context resolution

The server resolves project scope using the following precedence:

1. **Internal proxy context present** → trust internal context and ignore public `Authorization`.
2. Otherwise require `Authorization: Bearer <project_api_key>` and derive `project_id` from the key.

### Authorization rules

- Endpoints that accept a `workspace_id` must verify that the workspace belongs to the derived project context.
- Any request-provided `project_id`/`X-Project-ID` must be ignored for authorization decisions (and ideally removed from public request schemas).

## Proxy Embedding Contract

A gateway/wrapper is responsible for:

- Authenticating public requests (JWT, API keys, etc).
- Stripping any client-provided internal headers (`X-Project-ID`, internal auth headers) at the edge.
- Injecting a trusted internal context to the OSS server so the embedded OSS app does not need to validate public JWTs directly.

The OSS server is responsible for:

- Validating the injected internal context (signature/HMAC) and deriving `project_id` + principal identity from it.
- Never trusting internal context unless validation succeeds.

## Security Considerations (Private/Protected Deployments)

Even in protected networks, simplifying auth is still valuable:

- Eliminates ambiguous configuration that can silently mis-secure deployments.
- Prevents accidental cross-project operations due to stale/misconfigured `project_id`.
- Ensures browser features (dashboard, SSE) are compatible with auth and do not encourage disabling auth for convenience.

## Acceptance Checklist (for OSS launch readiness)

- `bdh` works with only `.beadhub` + `.aw/context` + `~/.config/aw/config.yaml` containing an account for the server.
- No public client sends `X-Project-ID` (CLI or browser).
- OSS server does not implement or document any public `X-API-Key` auth path.
- All project-scoped endpoints derive project server-side and verify workspace membership.
- Dashboard SSE works authenticated (no `EventSource` header limitation).
