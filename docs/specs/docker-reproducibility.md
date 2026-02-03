# Docker Reproducibility (Pin Toolchain Inputs)

The Docker build pins toolchain inputs:

- pnpm version (via `corepack prepare`) and `frontend/package.json` `packageManager`
- uv version (copied from `ghcr.io/astral-sh/uv:<version>`; digest pinning is preferred)

## Why This Matters

Even with a lockfile (`pnpm-lock.yaml`, `uv.lock`), unpinned *toolchain* inputs can cause rebuilds of the same git commit to break:

- A new pnpm release can change lockfile interpretation or CLI behavior.
- A new `uv` release can change resolution/install behavior, default flags, or wheel handling.
- If a user rebuilds an older tag for incident response, they can end up debugging “random” breakage unrelated to their changes.

This affects both OSS users building images and hosted build pipelines (less often, but still a source of surprise).

## Implementation

- Pin pnpm to a specific version (Corepack):
  - `corepack prepare pnpm@9.15.0 --activate`
  - and/or use a pinned `packageManager` field in `frontend/package.json`.
- Pin uv by digest (preferred) or at least by tag:
  - `COPY --from=ghcr.io/astral-sh/uv:0.9.22@sha256:<digest> /uv /usr/local/bin/uv`

## Operational Guidance

- Document the update process:
  - When bumping `uv.lock` / `pnpm-lock.yaml`, consider bumping the pinned tool versions at the same time.
- Prefer digest pinning for container images to eliminate registry tag drift.

## Acceptance Criteria

- Rebuilding the same commit weeks later should not “randomly” fail due to pnpm/uv changes.
- Docker builds remain cache-friendly (pins should not reduce caching).
