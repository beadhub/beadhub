from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from aweb.auth import validate_project_slug
from aweb.bootstrap import BootstrapIdentityResult, bootstrap_identity, ensure_project
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from beadhub.beads_sync import is_valid_alias, is_valid_human_name
from beadhub.db import DatabaseInfra, get_db_infra
from beadhub.names import CLASSIC_NAMES
from beadhub.rate_limit import enforce_init_rate_limit
from beadhub.redis_client import get_redis
from beadhub.roles import ROLE_MAX_LENGTH, is_valid_role, normalize_role, role_to_alias_prefix
from beadhub.routes.repos import canonicalize_git_url, extract_repo_name

router = APIRouter(prefix="/v1/init", tags=["init"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InitRequest(BaseModel):
    """Bootstrap an aweb identity and (optionally) a BeadHub workspace."""

    model_config = ConfigDict(extra="forbid")

    # aweb identity fields (protocol)
    project_slug: str = Field(default="", max_length=256)
    project_name: str = Field(default="", max_length=256)
    alias: str | None = Field(default=None, min_length=1, max_length=64)
    human_name: str = Field(default="", max_length=64)
    agent_type: str = Field(default="agent", max_length=32)
    lifetime: str = Field(default="ephemeral", pattern="^(persistent|ephemeral)$")
    custody: str | None = Field(default=None, pattern="^(self|custodial)$")

    # beadhub extension fields (optional)
    project_id: str | None = Field(default=None, max_length=36)
    repo_origin: str | None = Field(default=None, max_length=2048)
    role: str = Field(default="agent", max_length=ROLE_MAX_LENGTH)
    hostname: str = Field(default="", max_length=255)
    workspace_path: str = Field(default="", max_length=4096)

    @field_validator("project_slug")
    @classmethod
    def _validate_project_slug(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return ""
        return validate_project_slug(v)

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not is_valid_alias(v):
            raise ValueError("Invalid alias format")
        return v

    @field_validator("human_name")
    @classmethod
    def _validate_human_name(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not is_valid_human_name(v):
            raise ValueError("Invalid human_name format")
        return v

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: str) -> str:
        v = normalize_role((v or "").strip()) or "agent"
        if not is_valid_role(v):
            raise ValueError("Invalid role format")
        return v

    @field_validator("project_id")
    @classmethod
    def _validate_project_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        try:
            return str(UUID(v))
        except ValueError:
            raise ValueError("project_id must be a valid UUID")

    @field_validator("hostname")
    @classmethod
    def _validate_hostname(cls, v: str) -> str:
        v = (v or "").strip()
        if v and ("\x00" in v or any(ord(c) < 32 for c in v)):
            raise ValueError(
                "hostname contains invalid characters (null bytes or control characters)"
            )
        return v

    @field_validator("workspace_path")
    @classmethod
    def _validate_workspace_path(cls, v: str) -> str:
        v = (v or "").strip()
        if v and ("\x00" in v or any(ord(c) < 32 and c not in "\t\n" for c in v)):
            raise ValueError(
                "workspace_path contains invalid characters (null bytes or control characters)"
            )
        return v


class InitResponse(BaseModel):
    status: str = "ok"
    created_at: str
    api_key: str
    project_id: str
    project_slug: str
    agent_id: str
    repo_id: str | None = None
    canonical_origin: str | None = None
    workspace_id: str | None = None
    alias: str
    created: bool = False
    workspace_created: bool = False
    did: str | None = None
    custody: str | None = None
    lifetime: str = "ephemeral"


async def _infer_project_slug_from_repo(
    db_infra: DatabaseInfra, *, canonical_origin: str
) -> str | None:
    server_db = db_infra.get_manager("server")
    row = await server_db.fetch_one(
        """
        SELECT p.slug
        FROM {{tables.repos}} r
        JOIN {{tables.projects}} p ON r.project_id = p.id AND p.deleted_at IS NULL
        WHERE r.canonical_origin = $1 AND r.deleted_at IS NULL
        """,
        canonical_origin,
    )
    if not row:
        return None
    slug = (row.get("slug") or "").strip()
    return slug or None


async def _resolve_server_project(
    db_infra: DatabaseInfra, *, project_id: str
) -> tuple[str | None, str]:
    """Look up a project in server.projects by ID.

    Returns (tenant_id, slug). Raises 404 if the project doesn't exist.
    """
    server_db = db_infra.get_manager("server")
    row = await server_db.fetch_one(
        """
        SELECT tenant_id, slug
        FROM {{tables.projects}}
        WHERE id = $1 AND deleted_at IS NULL
        """,
        UUID(project_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="project_not_found: unknown project_id")
    tid = row.get("tenant_id")
    return (str(tid) if tid else None), row["slug"]


async def _suggest_name_prefix_for_project(db_infra: DatabaseInfra, *, project_id: str) -> str:
    aweb_db = db_infra.get_manager("aweb")
    rows = await aweb_db.fetch_all(
        """
        SELECT alias
        FROM {{tables.agents}}
        WHERE project_id = $1 AND deleted_at IS NULL
        ORDER BY alias
        """,
        UUID(project_id),
    )

    used_prefixes: set[str] = set()
    for row in rows:
        alias = (row.get("alias") or "").strip()
        if not alias:
            continue
        parts = alias.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            prefix = f"{parts[0]}-{parts[1]}".lower()
        else:
            prefix = parts[0].lower()
        if prefix:
            used_prefixes.add(prefix)

    for name in CLASSIC_NAMES:
        if name not in used_prefixes:
            return name

    for num in range(1, 100):
        for name in CLASSIC_NAMES:
            numbered = f"{name}-{num:02d}"
            if numbered not in used_prefixes:
                return numbered

    raise HTTPException(
        status_code=409,
        detail=f"All name prefixes are taken (tried {len(CLASSIC_NAMES)} names × 100 variants).",
    )


@router.post("", response_model=InitResponse)
async def init(
    request: Request,
    payload: InitRequest,
    db_infra: DatabaseInfra = Depends(get_db_infra),
    redis=Depends(get_redis),
) -> InitResponse:
    """Bootstrap identity and optionally register a BeadHub workspace.

    - Always mints a new `aw_sk_*` API key for the created/ensured agent.
    - If `repo_origin` is provided, also ensures the repo and creates a BeadHub workspace
      using `workspace_id = agent_id` (v1 mapping).
    """
    await enforce_init_rate_limit(request, redis)

    canonical_origin: str | None = None
    if payload.repo_origin is not None:
        canonical_origin = canonicalize_git_url(payload.repo_origin)

    project_slug = payload.project_slug
    if not project_slug:
        if canonical_origin is None:
            raise HTTPException(status_code=422, detail="project_slug is required")
        inferred = await _infer_project_slug_from_repo(db_infra, canonical_origin=canonical_origin)
        if inferred is None:
            raise HTTPException(status_code=422, detail="project_not_found: repo not registered")
        project_slug = inferred

    # When project_id is provided (cloud mode), validate it exists and look up
    # tenant_id so aweb creates its project record with the correct tenant scoping.
    tenant_id: str | None = None
    if payload.project_id:
        tenant_id, authoritative_slug = await _resolve_server_project(
            db_infra, project_id=payload.project_id
        )
        project_slug = authoritative_slug

    alias = (payload.alias or "").strip() or None
    if alias is None and canonical_origin is not None:
        ensured = await ensure_project(
            db_infra,
            project_slug=project_slug,
            project_name=payload.project_name or project_slug,
            project_id=payload.project_id,
            tenant_id=tenant_id,
        )
        prefix = await _suggest_name_prefix_for_project(db_infra, project_id=ensured.project_id)
        alias = f"{prefix}-{role_to_alias_prefix(payload.role)}"

    identity: BootstrapIdentityResult = await bootstrap_identity(
        db_infra,
        project_slug=project_slug,
        project_name=payload.project_name or project_slug,
        project_id=payload.project_id,
        tenant_id=tenant_id,
        alias=alias,
        human_name=payload.human_name or "",
        agent_type=payload.agent_type,
        lifetime=payload.lifetime,
        # custody=None → aweb defaults to "custodial" (server holds the signing key)
        custody=payload.custody,
    )

    if canonical_origin is None:
        return InitResponse(
            created_at=_now_iso(),
            api_key=identity.api_key,
            project_id=identity.project_id,
            project_slug=identity.project_slug,
            agent_id=identity.agent_id,
            alias=identity.alias,
            created=identity.created,
            did=identity.did,
            custody=identity.custody,
            lifetime=identity.lifetime,
        )

    server_db = db_infra.get_manager("server")

    repo_name = extract_repo_name(canonical_origin)
    workspace_created = False

    async with server_db.transaction() as tx:
        # When project_id was provided by the caller (cloud mode), the project
        # already exists in server.projects — skip the upsert to avoid
        # overwriting tenant_id or other cloud-managed fields.
        if not payload.project_id:
            await tx.execute(
                """
                INSERT INTO {{tables.projects}} (id, tenant_id, slug, name, deleted_at)
                VALUES ($1, NULL, $2, $3, NULL)
                ON CONFLICT (id)
                DO UPDATE SET slug = EXCLUDED.slug, name = EXCLUDED.name, deleted_at = NULL
                """,
                UUID(identity.project_id),
                identity.project_slug,
                identity.project_name or None,
            )

        repo = await tx.fetch_one(
            """
            INSERT INTO {{tables.repos}} (project_id, origin_url, canonical_origin, name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (project_id, canonical_origin)
            DO UPDATE SET origin_url = EXCLUDED.origin_url, deleted_at = NULL
            RETURNING id
            """,
            UUID(identity.project_id),
            payload.repo_origin,
            canonical_origin,
            repo_name,
        )
        repo_id = str(repo["id"])

        existing = await tx.fetch_one(
            """
            SELECT
                w.workspace_id,
                w.repo_id,
                w.alias,
                r.canonical_origin AS existing_canonical_origin
            FROM {{tables.workspaces}} w
            LEFT JOIN {{tables.repos}} r ON w.repo_id = r.id
            WHERE w.workspace_id = $1 AND w.project_id = $2
            """,
            UUID(identity.agent_id),
            UUID(identity.project_id),
        )

        if existing is None:
            workspace_created = True
            await tx.execute(
                """
                INSERT INTO {{tables.workspaces}}
                    (workspace_id, project_id, repo_id, alias, human_name, role, hostname, workspace_path)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                UUID(identity.agent_id),
                UUID(identity.project_id),
                UUID(repo_id),
                identity.alias,
                payload.human_name or "",
                payload.role,
                payload.hostname or None,
                payload.workspace_path or None,
            )
        else:
            existing_repo_id = existing.get("repo_id")
            existing_canonical = existing.get("existing_canonical_origin")
            if existing_repo_id is None or str(existing_repo_id) != repo_id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "workspace_repo_mismatch: "
                        f"alias '{identity.alias}' (workspace_id={identity.agent_id}) is already registered "
                        f"for repo '{existing_canonical or existing_repo_id}'. "
                        f"Cannot initialize the same agent for repo '{canonical_origin}'. "
                        "Choose a different alias (new agent/worktree) or initialize from the original repo."
                    ),
                )

            await tx.execute(
                """
                UPDATE {{tables.workspaces}}
                SET repo_id = $3,
                    alias = $4,
                    human_name = $5,
                    role = $6,
                    hostname = $7,
                    workspace_path = $8,
                    deleted_at = NULL
                WHERE workspace_id = $1 AND project_id = $2
                """,
                UUID(identity.agent_id),
                UUID(identity.project_id),
                UUID(repo_id),
                identity.alias,
                payload.human_name or "",
                payload.role,
                payload.hostname or None,
                payload.workspace_path or None,
            )

    return InitResponse(
        created_at=_now_iso(),
        api_key=identity.api_key,
        project_id=identity.project_id,
        project_slug=identity.project_slug,
        agent_id=identity.agent_id,
        repo_id=repo_id,
        canonical_origin=canonical_origin,
        workspace_id=identity.agent_id,
        alias=identity.alias,
        created=identity.created,
        workspace_created=workspace_created,
        did=identity.did,
        custody=identity.custody,
        lifetime=identity.lifetime,
    )
