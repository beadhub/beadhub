from __future__ import annotations

from typing import Optional
from uuid import UUID

from redis.asyncio import Redis

from ..db import DatabaseInfra
from ..presence import get_workspace_id_by_alias
from .routes.repos import canonicalize_git_url, extract_repo_name


async def ensure_repo(
    db: DatabaseInfra,
    project_id: UUID,
    origin_url: str,
) -> UUID:
    """Ensure a repo exists for the given project and origin."""
    canonical_origin = canonicalize_git_url(origin_url)
    repo_name = extract_repo_name(canonical_origin)

    server_db = db.get_manager("server")
    result = await server_db.fetch_one(
        """
        INSERT INTO {{tables.repos}} (project_id, origin_url, canonical_origin, name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (project_id, canonical_origin)
        DO UPDATE SET origin_url = EXCLUDED.origin_url, deleted_at = NULL
        RETURNING id
        """,
        project_id,
        origin_url,
        canonical_origin,
        repo_name,
    )
    return result["id"]


async def upsert_workspace(
    db: DatabaseInfra,
    workspace_id: str,
    project_id: UUID,
    repo_id: UUID,
    alias: str,
    human_name: str,
    role: Optional[str] = None,
    hostname: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> None:
    """Upsert a workspace into the persistent registry."""
    server_db = db.get_manager("server")
    await server_db.execute(
        """
        INSERT INTO {{tables.workspaces}} (workspace_id, project_id, repo_id, alias, human_name, role, hostname, workspace_path, last_seen_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        ON CONFLICT (workspace_id) DO UPDATE SET
            repo_id = COALESCE({{tables.workspaces}}.repo_id, EXCLUDED.repo_id),
            human_name = EXCLUDED.human_name,
            role = COALESCE(EXCLUDED.role, {{tables.workspaces}}.role),
            hostname = COALESCE({{tables.workspaces}}.hostname, EXCLUDED.hostname),
            workspace_path = COALESCE({{tables.workspaces}}.workspace_path, EXCLUDED.workspace_path),
            workspace_type = CASE
                WHEN {{tables.workspaces}}.repo_id IS NULL AND EXCLUDED.repo_id IS NOT NULL
                    THEN 'agent'
                ELSE {{tables.workspaces}}.workspace_type
            END,
            deleted_at = NULL,
            last_seen_at = NOW(),
            updated_at = NOW()
        """,
        workspace_id,
        project_id,
        repo_id,
        alias,
        human_name,
        role,
        hostname,
        workspace_path,
    )


async def check_alias_collision(
    db: DatabaseInfra,
    redis: Redis,
    project_id: UUID,
    workspace_id: str,
    alias: str,
) -> Optional[str]:
    """Check if an alias is already used by another workspace in the project."""
    server_db = db.get_manager("server")

    row = await server_db.fetch_one(
        """
        SELECT workspace_id
        FROM {{tables.workspaces}}
        WHERE project_id = $1 AND alias = $2 AND workspace_id != $3 AND deleted_at IS NULL
        LIMIT 1
        """,
        project_id,
        alias,
        UUID(workspace_id),
    )
    if row:
        return str(row["workspace_id"])

    row = await server_db.fetch_one(
        """
        SELECT DISTINCT workspace_id
        FROM {{tables.task_claims}}
        WHERE project_id = $1 AND alias = $2 AND workspace_id != $3
        LIMIT 1
        """,
        project_id,
        alias,
        UUID(workspace_id),
    )
    if row:
        return str(row["workspace_id"])

    colliding_workspace = await get_workspace_id_by_alias(redis, str(project_id), alias)
    if colliding_workspace and colliding_workspace != workspace_id:
        return colliding_workspace

    return None
