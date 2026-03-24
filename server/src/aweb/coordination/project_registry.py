from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException


async def ensure_server_project_row(
    *,
    server_db,
    aweb_db,
    project_id: str,
    project_slug: str,
    project_name: str,
) -> None:
    """Ensure a coordination project row exists without dropping owner metadata.

    The hosted wrapper owns project creation and explicit owner fields in
    `server.projects`. Coordination routes should reuse that row when it already
    exists instead of re-inserting a partial copy. When bootstrapping a fresh
    row locally, we can only recover personal ownership from `aweb.projects`.
    """

    project_uuid = UUID(project_id)
    existing = await server_db.fetch_one(
        """
        SELECT id
        FROM {{tables.projects}}
        WHERE id = $1
        """,
        project_uuid,
    )
    if existing:
        await server_db.execute(
            """
            UPDATE {{tables.projects}}
            SET slug = $2,
                name = $3,
                deleted_at = NULL
            WHERE id = $1
            """,
            project_uuid,
            project_slug,
            project_name or None,
        )
        return

    aweb_project = await aweb_db.fetch_one(
        """
        SELECT tenant_id, slug, name
        FROM {{tables.projects}}
        WHERE project_id = $1 AND deleted_at IS NULL
        """,
        project_uuid,
    )
    if not aweb_project:
        raise HTTPException(
            status_code=500,
            detail="Project metadata missing for coordination bootstrap",
        )

    owner_user_id = aweb_project.get("tenant_id")
    if owner_user_id is None:
        raise HTTPException(
            status_code=500,
            detail="Project owner metadata missing for coordination bootstrap",
        )

    await server_db.execute(
        """
        INSERT INTO {{tables.projects}}
            (id, tenant_id, owner_type, owner_user_id, owner_org_id, slug, name, deleted_at)
        VALUES
            ($1, $2, 'user', $2, NULL, $3, $4, NULL)
        """,
        project_uuid,
        owner_user_id,
        (project_slug or aweb_project.get("slug") or "").strip() or str(project_uuid),
        (project_name or aweb_project.get("name") or "").strip() or None,
    )
