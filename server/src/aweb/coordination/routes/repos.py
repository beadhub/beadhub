"""Aweb coordination repo endpoints.

Provides repository registration for standalone coordination deployments. Used by `aw init` and `aw use` to register
git repos within a project and obtain a repo_id (UUID).
"""

from __future__ import annotations

import logging
import re
import uuid as uuid_module
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis

from aweb.bootstrap import delete_agent_identity

from ...db import DatabaseInfra, get_db_infra
from ...pagination import encode_cursor, validate_pagination_params
from ...presence import clear_workspace_presence
from ...redis_client import get_redis

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/v1/repos", tags=["repos"])


def canonicalize_git_url(origin_url: str) -> str:
    """
    Normalize a git origin URL to canonical form.

    Converts various git URL formats to a consistent canonical form:
    - git@github.com:org/repo.git -> github.com/org/repo
    - https://github.com/org/repo.git -> github.com/org/repo
    - ssh://git@github.com:22/org/repo.git -> github.com/org/repo

    Args:
        origin_url: Git origin URL in any format

    Returns:
        Canonical form: host/path (e.g., github.com/org/repo)

    Raises:
        ValueError: If the URL cannot be parsed
    """
    if not origin_url or not origin_url.strip():
        raise ValueError("Empty origin URL")

    url = origin_url.strip()

    # Handle SSH format: git@host:path
    ssh_match = re.match(r"^git@([^:]+):(.+)$", url)
    if ssh_match:
        host = ssh_match.group(1)
        path = ssh_match.group(2)
    else:
        # Handle URL format (https://, http://, ssh://)
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid git URL: {origin_url}")

        host = parsed.hostname
        if not host:
            raise ValueError(f"Invalid git URL: {origin_url}")

        # For ssh:// format with user@host:port, parsed.path starts with /
        path = parsed.path.lstrip("/")

    # Remove .git extension
    if path.endswith(".git"):
        path = path[:-4]

    # Remove trailing slash
    path = path.rstrip("/")

    if not path:
        raise ValueError(f"Invalid git URL (no path): {origin_url}")

    return f"{host}/{path}"


def extract_repo_name(canonical_origin: str) -> str:
    """
    Extract repo name from canonical origin.

    Args:
        canonical_origin: Canonical origin (e.g., github.com/org/repo)

    Returns:
        Repo name (last path component, e.g., repo)
    """
    return canonical_origin.rsplit("/", 1)[-1]


class RepoLookupRequest(BaseModel):
    """Request body for POST /v1/repos/lookup."""

    origin_url: str = Field(..., min_length=1, max_length=2048)

    @field_validator("origin_url")
    @classmethod
    def validate_origin_url(cls, v: str) -> str:
        """Validate origin_url can be canonicalized."""
        try:
            canonicalize_git_url(v)
        except ValueError as e:
            raise ValueError(f"Invalid origin_url: {e}")
        return v


class RepoLookupResponse(BaseModel):
    """Response for POST /v1/repos/lookup."""

    repo_id: str
    project_id: str
    project_slug: str
    canonical_origin: str
    name: str


class RepoLookupCandidate(BaseModel):
    """A candidate repo/project pair when lookup is ambiguous."""

    repo_id: str
    project_id: str
    project_slug: str


@router.post("/lookup")
async def lookup_repo(
    payload: RepoLookupRequest,
    db: DatabaseInfra = Depends(get_db_infra),
) -> RepoLookupResponse:
    """
    Look up a repo by origin URL. Returns the repo and its project if found.

    This is used by `aw init` / `aw use` to detect if a repo is already registered,
    allowing automatic project detection.

    Returns:
    - 200 with repo info if exactly one match
    - 404 if no matches
    - 409 with candidates if multiple projects have the same repo
    """
    server_db = db.get_manager("server")
    aweb_db = db.get_manager("aweb")

    canonical_origin = canonicalize_git_url(payload.origin_url)

    # Fetch ALL matching repos (not just the first one)
    results = await server_db.fetch_all(
        """
        SELECT r.id as repo_id, r.canonical_origin, r.name,
               p.id as project_id, p.slug as project_slug
        FROM {{tables.repos}} r
        JOIN {{tables.projects}} p ON r.project_id = p.id AND p.deleted_at IS NULL
        WHERE r.canonical_origin = $1 AND r.deleted_at IS NULL
        ORDER BY p.slug
        """,
        canonical_origin,
    )

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Repo not found: {canonical_origin}",
        )

    if len(results) == 1:
        result = results[0]
        return RepoLookupResponse(
            repo_id=str(result["repo_id"]),
            project_id=str(result["project_id"]),
            project_slug=result["project_slug"],
            canonical_origin=result["canonical_origin"],
            name=result["name"],
        )

    # Multiple matches - return 409 with candidates
    candidates = [
        RepoLookupCandidate(
            repo_id=str(r["repo_id"]),
            project_id=str(r["project_id"]),
            project_slug=r["project_slug"],
        )
        for r in results
    ]
    project_slugs = [c.project_slug for c in candidates]

    raise HTTPException(
        status_code=409,
        detail={
            "message": f"Repo {canonical_origin} exists in multiple projects: {', '.join(project_slugs)}. "
            "Authenticate with the correct project account, then run 'aw init' or 'aw use' from this repo.",
            "canonical_origin": canonical_origin,
            "candidates": [c.model_dump() for c in candidates],
        },
    )


class RepoEnsureRequest(BaseModel):
    """Request body for POST /v1/repos/ensure."""

    project_id: str = Field(..., min_length=36, max_length=36)
    origin_url: str = Field(..., min_length=1, max_length=2048)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        """Validate project_id is a valid UUID."""
        try:
            uuid_module.UUID(v)
        except ValueError:
            raise ValueError("Invalid project_id: must be a valid UUID")
        return v

    @field_validator("origin_url")
    @classmethod
    def validate_origin_url(cls, v: str) -> str:
        """Validate origin_url can be canonicalized."""
        try:
            canonicalize_git_url(v)
        except ValueError as e:
            raise ValueError(f"Invalid origin_url: {e}")
        return v


class RepoEnsureResponse(BaseModel):
    """Response for POST /v1/repos/ensure."""

    repo_id: str
    canonical_origin: str
    name: str
    created: bool


@router.post("/ensure")
async def ensure_repo(
    payload: RepoEnsureRequest,
    db: DatabaseInfra = Depends(get_db_infra),
) -> RepoEnsureResponse:
    """
    Get or create a repo by origin URL. Used by `aw init` / `aw use` in standalone coordination deployments.

    If a repo with the same canonical origin exists in the project, returns it
    with created=false (and updates the origin_url to the new value).
    If it doesn't exist, creates it and returns with created=true.

    The canonical_origin is computed by normalizing the origin_url. Different
    URL formats (SSH vs HTTPS) that refer to the same repo will match.
    """
    server_db = db.get_manager("server")

    # First verify the project exists and is not soft-deleted
    project = await server_db.fetch_one(
        "SELECT id FROM {{tables.projects}} WHERE id = $1 AND deleted_at IS NULL",
        payload.project_id,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    canonical_origin = canonicalize_git_url(payload.origin_url)
    name = extract_repo_name(canonical_origin)

    # Use INSERT ON CONFLICT DO UPDATE to handle race conditions.
    # The (xmax = 0) check detects INSERT vs UPDATE: xmax is 0 for new rows,
    # non-zero when updated (PostgreSQL stores the updating transaction ID there).
    # Also clear deleted_at to undelete soft-deleted repos when re-registered.
    result = await server_db.fetch_one(
        """
        INSERT INTO {{tables.repos}} (project_id, origin_url, canonical_origin, name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (project_id, canonical_origin)
        DO UPDATE SET origin_url = EXCLUDED.origin_url, deleted_at = NULL
        RETURNING id, canonical_origin, name, (xmax = 0) AS created
        """,
        payload.project_id,
        payload.origin_url,
        canonical_origin,
        name,
    )

    created = result["created"]
    if created:
        logger.info(
            "Repo created: project=%s canonical=%s id=%s",
            payload.project_id,
            canonical_origin,
            result["id"],
        )
    else:
        logger.info(
            "Repo found: project=%s canonical=%s id=%s",
            payload.project_id,
            canonical_origin,
            result["id"],
        )

    return RepoEnsureResponse(
        repo_id=str(result["id"]),
        canonical_origin=result["canonical_origin"],
        name=result["name"],
        created=created,
    )


class RepoSummary(BaseModel):
    """Summary of a repo for list view."""

    id: str
    project_id: str
    canonical_origin: str
    name: str
    created_at: datetime
    workspace_count: int


class RepoListResponse(BaseModel):
    """Response for GET /v1/repos."""

    repos: list[RepoSummary]
    has_more: bool = False
    next_cursor: Optional[str] = None


@router.get("")
async def list_repos(
    project_id: Optional[UUID] = Query(default=None, description="Filter by project ID"),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=200,
        description="Maximum number of repos to return (default 50, max 200)",
    ),
    cursor: Optional[str] = Query(
        default=None, description="Pagination cursor from previous response"
    ),
    db: DatabaseInfra = Depends(get_db_infra),
) -> RepoListResponse:
    """
    List repos with optional project filter and cursor-based pagination.

    Returns active (non-deleted) repos, optionally filtered by project_id.
    Each repo includes a count of active workspaces.

    Results are ordered by (created_at, id) for deterministic pagination
    that remains stable across inserts.
    """
    try:
        validated_limit, cursor_data = validate_pagination_params(limit, cursor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    server_db = db.get_manager("server")

    query = """
        SELECT
            r.id,
            r.project_id,
            r.canonical_origin,
            r.name,
            r.created_at,
            COUNT(w.workspace_id) FILTER (WHERE w.deleted_at IS NULL) AS workspace_count
        FROM {{tables.repos}} r
        LEFT JOIN {{tables.workspaces}} w ON w.repo_id = r.id
        WHERE r.deleted_at IS NULL
    """

    params: list = []
    param_idx = 1

    if project_id:
        query += f" AND r.project_id = ${param_idx}"
        params.append(str(project_id))
        param_idx += 1

    # Apply cursor filter (created_at, id) for deterministic pagination
    if cursor_data and "created_at" in cursor_data and "id" in cursor_data:
        try:
            cursor_created_at = datetime.fromisoformat(cursor_data["created_at"])
            cursor_id = UUID(cursor_data["id"])
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid cursor: {e}")
        query += f" AND (r.created_at, r.id) > (${param_idx}, ${param_idx + 1})"
        params.extend([cursor_created_at, cursor_id])
        param_idx += 2

    query += """
        GROUP BY r.id, r.project_id, r.canonical_origin, r.name, r.created_at
        ORDER BY r.created_at, r.id
    """

    # Fetch limit + 1 to detect has_more
    query += f" LIMIT ${param_idx}"
    params.append(validated_limit + 1)

    rows = await server_db.fetch_all(query, *params)

    # Check if there are more results
    has_more = len(rows) > validated_limit
    rows = rows[:validated_limit]  # Trim to requested limit

    # Generate next_cursor if there are more results
    next_cursor = None
    if has_more and rows:
        last_row = rows[-1]
        next_cursor = encode_cursor(
            {
                "created_at": last_row["created_at"].isoformat(),
                "id": str(last_row["id"]),
            }
        )

    return RepoListResponse(
        repos=[
            RepoSummary(
                id=str(row["id"]),
                project_id=str(row["project_id"]),
                canonical_origin=row["canonical_origin"],
                name=row["name"],
                created_at=row["created_at"],
                workspace_count=row["workspace_count"],
            )
            for row in rows
        ],
        has_more=has_more,
        next_cursor=next_cursor,
    )


class RepoDeleteResponse(BaseModel):
    """Response for DELETE /v1/repos/{id}."""

    id: str
    workspaces_deleted: int
    claims_deleted: int
    presence_cleared: int


@router.delete("/{repo_id}")
async def delete_repo(
    repo_id: UUID,
    db: DatabaseInfra = Depends(get_db_infra),
    redis: Redis = Depends(get_redis),
) -> RepoDeleteResponse:
    """
    Soft-delete a repo and cascade to ephemeral workspaces.

    This operation:
    1. Sets deleted_at on the repo
    2. Soft-deletes all workspaces in the repo (sets deleted_at)
    3. Deletes all task claims for those workspaces
    4. Clears Redis presence for those workspaces

    Returns counts of affected resources.
    """
    server_db = db.get_manager("server")

    # Verify repo exists and is not already deleted
    repo = await server_db.fetch_one(
        """
        SELECT id, project_id FROM {{tables.repos}}
        WHERE id = $1 AND deleted_at IS NULL
        """,
        str(repo_id),
    )
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    # Get all workspace_ids for this repo
    workspace_rows = await server_db.fetch_all(
        """
        SELECT workspace_id FROM {{tables.workspaces}}
        WHERE repo_id = $1 AND deleted_at IS NULL
        """,
        str(repo_id),
    )
    workspace_ids = [str(row["workspace_id"]) for row in workspace_rows]

    if workspace_ids:
        persistent_rows = await aweb_db.fetch_all(
            """
            SELECT agent_id, alias
            FROM {{tables.agents}}
            WHERE project_id = $1
              AND agent_id = ANY($2::uuid[])
              AND deleted_at IS NULL
              AND lifetime = 'persistent'
            ORDER BY alias
            """,
            str(repo["project_id"]),
            workspace_ids,
        )
        if persistent_rows:
            aliases = ", ".join(str(row["alias"]) for row in persistent_rows[:5])
            raise HTTPException(
                status_code=409,
                detail=(
                    "Repo deletion cannot delete persistent identities. "
                    f"Detach or archive the affected identities first: {aliases}"
                ),
            )

    # Soft-delete workspaces manually (cannot use FK cascade for soft-delete).
    # The FK SET NULL only triggers when repo is hard-deleted (e.g., via project cascade),
    # at which point the trigger in 005_workspaces.sql auto-sets deleted_at.
    if workspace_ids:
        await server_db.execute(
            """
            UPDATE {{tables.workspaces}}
            SET deleted_at = NOW()
            WHERE repo_id = $1 AND deleted_at IS NULL
            """,
            str(repo_id),
        )

    # Cascade to aweb agents: deactivate identities, keys, and free aliases.
    for ws_id in workspace_ids:
        await delete_agent_identity(db, agent_id=ws_id, project_id=str(repo["project_id"]))

    # Delete claims for these workspaces
    claims_deleted = 0
    if workspace_ids:
        result = await server_db.fetch_one(
            """
            WITH deleted AS (
                DELETE FROM {{tables.task_claims}}
                WHERE workspace_id = ANY($1::uuid[])
                RETURNING id
            )
            SELECT COUNT(*) as count FROM deleted
            """,
            workspace_ids,
        )
        claims_deleted = result["count"] if result else 0

    # Clear Redis presence
    presence_cleared = await clear_workspace_presence(redis, workspace_ids)

    # Soft-delete the repo
    await server_db.execute(
        """
        UPDATE {{tables.repos}}
        SET deleted_at = NOW()
        WHERE id = $1
        """,
        str(repo_id),
    )

    logger.info(
        "Repo soft-deleted: id=%s workspaces=%d claims=%d presence=%d",
        repo_id,
        len(workspace_ids),
        claims_deleted,
        presence_cleared,
    )

    return RepoDeleteResponse(
        id=str(repo_id),
        workspaces_deleted=len(workspace_ids),
        claims_deleted=claims_deleted,
        presence_cleared=presence_cleared,
    )
