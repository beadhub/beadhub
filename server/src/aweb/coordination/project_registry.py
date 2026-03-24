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

    The server schema may be used in pure OSS mode or embedded inside the
    hosted wrapper. The OSS ownership model is generic: `owner_type` plus
    `owner_ref` when ownership metadata exists. Standalone bootstrap must
    continue to work even when no tenant or cloud-specific owner fields exist.
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
        SELECT tenant_id, slug, name, owner_type, owner_ref
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

    owner_type = (aweb_project.get("owner_type") or "").strip() or None
    owner_ref = (aweb_project.get("owner_ref") or "").strip() or None
    tenant_id = aweb_project.get("tenant_id")
    await server_db.execute(
        """
        INSERT INTO {{tables.projects}}
            (id, tenant_id, owner_type, owner_ref, owner_user_id, owner_org_id, slug, name, deleted_at)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8, NULL)
        """,
        project_uuid,
        tenant_id,
        owner_type,
        owner_ref,
        None,
        None,
        (project_slug or aweb_project.get("slug") or "").strip() or str(project_uuid),
        (project_name or aweb_project.get("name") or "").strip() or None,
    )
