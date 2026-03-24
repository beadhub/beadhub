"""Projection helpers owned by the OSS aweb package.

These keep the local `aweb` protocol tables aligned with the surrounding
coordination schema without depending on the Cloud wrapper package.
"""

from __future__ import annotations

import json
import uuid as uuid_module
from typing import Optional

from pgdbm import AsyncDatabaseManager, TransactionManager

DatabaseHandle = AsyncDatabaseManager | TransactionManager


async def ensure_aweb_project_and_agent(
    *,
    oss_db: DatabaseHandle,
    aweb_db: Optional[DatabaseHandle],
    project_id: str,
    workspace_id: str,
    alias: str,
    human_name: str,
    agent_type: str = "agent",
    role: str | None = None,
    program: str | None = None,
    context: dict | None = None,
) -> None:
    """Ensure the local project + agent projection rows exist for this workspace."""
    if aweb_db is None:
        return

    try:
        project_uuid = uuid_module.UUID(str(project_id))
        workspace_uuid = uuid_module.UUID(str(workspace_id))
    except ValueError:
        return

    context_json = json.dumps(context) if context is not None else None

    project_row = await oss_db.fetch_one(
        """
        SELECT id, tenant_id, owner_type, owner_ref, slug, name
        FROM {{tables.projects}}
        WHERE id = $1 AND deleted_at IS NULL
        """,
        project_uuid,
    )
    if not project_row:
        return

    tenant_id = project_row.get("tenant_id")
    raw_owner_type = (project_row.get("owner_type") or "").strip()
    raw_owner_ref = (project_row.get("owner_ref") or "").strip()
    owner_type = raw_owner_type or None
    owner_ref = raw_owner_ref or None
    slug = (project_row.get("slug") or str(project_uuid)).strip()
    name = (project_row.get("name") or "").strip()

    await aweb_db.execute(
        """
        INSERT INTO {{tables.projects}} (project_id, tenant_id, slug, name, owner_type, owner_ref, deleted_at)
        VALUES ($1, $2, $3, $4, $5, $6, NULL)
        ON CONFLICT (project_id)
        DO UPDATE SET tenant_id = EXCLUDED.tenant_id, slug = EXCLUDED.slug,
                      name = EXCLUDED.name,
                      owner_type = COALESCE(EXCLUDED.owner_type, {{tables.projects}}.owner_type),
                      owner_ref = COALESCE(EXCLUDED.owner_ref, {{tables.projects}}.owner_ref),
                      deleted_at = NULL
        """,
        project_uuid,
        tenant_id,
        slug,
        name,
        owner_type,
        owner_ref or None,
    )

    existing_alias = await aweb_db.fetch_one(
        """
        SELECT agent_id
        FROM {{tables.agents}}
        WHERE project_id = $1 AND alias = $2 AND deleted_at IS NULL
        """,
        project_uuid,
        alias,
    )
    if existing_alias and str(existing_alias["agent_id"]) != str(workspace_uuid):
        raise ValueError(
            f"Alias '{alias}' is already used by another agent. Choose a different alias."
        )

    updated = await aweb_db.fetch_one(
        """
        UPDATE {{tables.agents}}
        SET project_id = $2, alias = $3, human_name = $4, agent_type = $5,
            role = COALESCE($6, role),
            program = COALESCE($7, program),
            context = COALESCE($8, context),
            deleted_at = NULL
        WHERE agent_id = $1
        RETURNING agent_id
        """,
        workspace_uuid,
        project_uuid,
        alias,
        human_name or "",
        agent_type or "agent",
        role,
        program,
        context_json,
    )
    if not updated:
        inserted = await aweb_db.fetch_one(
            """
            INSERT INTO {{tables.agents}} (
                agent_id, project_id, alias, human_name, agent_type,
                role, program, context, deleted_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NULL)
            ON CONFLICT (project_id, alias) WHERE deleted_at IS NULL
            DO NOTHING
            RETURNING agent_id
            """,
            workspace_uuid,
            project_uuid,
            alias,
            human_name or "",
            agent_type or "agent",
            role,
            program,
            context_json,
        )
        if not inserted:
            winner = await aweb_db.fetch_one(
                """
                SELECT agent_id
                FROM {{tables.agents}}
                WHERE project_id = $1 AND alias = $2 AND deleted_at IS NULL
                """,
                project_uuid,
                alias,
            )
            if not winner:
                raise RuntimeError(
                    f"aweb agent insert returned no row and alias not found: project={project_id} alias={alias}"
                )
            if str(winner["agent_id"]) != str(workspace_uuid):
                raise ValueError(
                    f"Alias '{alias}' is already used by another agent. Choose a different alias."
                )
