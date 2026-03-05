"""Bead claim lifecycle operations.

Shared by the bdh sync handler (beads mode) and the mutation hooks
(native aweb-tasks mode).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

if TYPE_CHECKING:
    from .db import DatabaseInfra

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_task_apex(
    db_infra: DatabaseInfra,
    project_id: str,
    task_ref: str,
    max_depth: int = 20,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Walk aweb tasks parent_task_id chain to find the root task.

    Falls back to aweb.tasks when beads_issues has no data (native mode).
    Returns (root_task_ref, None, None) since aweb tasks have no repo/branch.
    """
    aweb_db = db_infra.get_manager("aweb")

    # Look up the project slug for task_ref reconstruction
    project = await aweb_db.fetch_one(
        "SELECT slug FROM {{tables.projects}} WHERE project_id = $1 AND deleted_at IS NULL",
        UUID(project_id),
    )
    if not project:
        return None, None, None
    slug = project["slug"]

    # Parse task_number from task_ref (format: {slug}-{number:03d})
    prefix = slug + "-"
    if not task_ref.startswith(prefix):
        return None, None, None
    try:
        task_number = int(task_ref[len(prefix) :])
    except ValueError:
        return None, None, None

    current = await aweb_db.fetch_one(
        """
        SELECT task_id, task_number, parent_task_id
        FROM {{tables.tasks}}
        WHERE project_id = $1 AND task_number = $2 AND deleted_at IS NULL
        """,
        UUID(project_id),
        task_number,
    )
    if not current:
        return None, None, None

    # Walk parent chain to root
    depth = 0
    while current.get("parent_task_id") and depth < max_depth:
        parent = await aweb_db.fetch_one(
            """
            SELECT task_id, task_number, parent_task_id
            FROM {{tables.tasks}}
            WHERE task_id = $1 AND deleted_at IS NULL
            """,
            current["parent_task_id"],
        )
        if not parent:
            break
        current = parent
        depth += 1

    apex_ref = f"{slug}-{current['task_number']:03d}"
    return apex_ref, None, None


async def resolve_claim_apex(
    db_infra: DatabaseInfra,
    project_id: str,
    bead_id: str,
    max_depth: int = 20,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve the apex for a bead by walking parent_id links.

    Returns (apex_bead_id, apex_repo_name, apex_branch). If the bead isn't found
    in beads_issues, returns (None, None, None).
    """
    beads_db = db_infra.get_manager("beads")
    current = await beads_db.fetch_one(
        """
        SELECT bead_id, repo, branch, parent_id
        FROM {{tables.beads_issues}}
        WHERE project_id = $1 AND bead_id = $2
        ORDER BY synced_at DESC
        LIMIT 1
        """,
        UUID(project_id),
        bead_id,
    )
    if not current:
        return await _resolve_task_apex(db_infra, project_id, bead_id, max_depth)

    depth = 0
    while current.get("parent_id") and depth < max_depth:
        parent = current["parent_id"]
        if isinstance(parent, str):
            try:
                parent = json.loads(parent)
            except (json.JSONDecodeError, RecursionError):
                break
        if not isinstance(parent, dict):
            break
        parent_repo = parent.get("repo")
        parent_branch = parent.get("branch")
        parent_bead_id = parent.get("bead_id")
        if not parent_repo or not parent_branch or not parent_bead_id:
            break

        parent_row = await beads_db.fetch_one(
            """
            SELECT bead_id, repo, branch, parent_id
            FROM {{tables.beads_issues}}
            WHERE project_id = $1
              AND repo = $2
              AND branch = $3
              AND bead_id = $4
            ORDER BY synced_at DESC
            LIMIT 1
            """,
            UUID(project_id),
            parent_repo,
            parent_branch,
            parent_bead_id,
        )
        if not parent_row:
            break
        current = parent_row
        depth += 1

    return current["bead_id"], current["repo"], current["branch"]


async def upsert_claim(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
    alias: str,
    human_name: str,
    bead_id: str,
) -> Optional[dict[str, Any]]:
    """Attempt to claim a bead. Returns None on success, or the conflicting
    claim dict (with alias, human_name, workspace_id) if already held by
    another workspace."""
    server_db = db_infra.get_manager("server")

    # Resolve apex (root parent) for this bead
    apex_bead_id, apex_repo_name, apex_branch = await resolve_claim_apex(
        db_infra, project_id, bead_id
    )

    async with server_db.transaction() as tx:
        # Check if another workspace already holds this claim.
        existing = await tx.fetch_one(
            """
            SELECT workspace_id, alias, human_name
            FROM {{tables.bead_claims}}
            WHERE project_id = $1 AND bead_id = $2 AND workspace_id != $3
            """,
            UUID(project_id),
            bead_id,
            UUID(workspace_id),
        )
        if existing:
            return {
                "workspace_id": str(existing["workspace_id"]),
                "alias": existing["alias"],
                "human_name": existing["human_name"],
            }

        await tx.execute(
            """
            INSERT INTO {{tables.bead_claims}} (
                project_id, workspace_id, alias, human_name, bead_id,
                apex_bead_id, apex_repo_name, apex_branch, claimed_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (project_id, bead_id, workspace_id)
            DO UPDATE SET
                alias = EXCLUDED.alias,
                human_name = EXCLUDED.human_name,
                apex_bead_id = EXCLUDED.apex_bead_id,
                apex_repo_name = EXCLUDED.apex_repo_name,
                apex_branch = EXCLUDED.apex_branch,
                claimed_at = EXCLUDED.claimed_at
            """,
            UUID(project_id),
            UUID(workspace_id),
            alias,
            human_name,
            bead_id,
            apex_bead_id,
            apex_repo_name,
            apex_branch,
            _now(),
        )

    # Update workspace focus_apex fields for team status display
    if apex_bead_id:
        await server_db.execute(
            """
            UPDATE {{tables.workspaces}}
            SET focus_apex_bead_id = $1,
                focus_apex_repo_name = $2,
                focus_apex_branch = $3,
                focus_updated_at = NOW(),
                updated_at = NOW()
            WHERE project_id = $4 AND workspace_id = $5
            """,
            apex_bead_id,
            apex_repo_name,
            apex_branch,
            UUID(project_id),
            UUID(workspace_id),
        )

    return None


async def release_bead_claims(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    bead_id: str,
    workspace_id: str | None = None,
) -> None:
    """Release claims on a bead and update affected workspaces' focus.

    If workspace_id is provided, only that workspace's claim is removed.
    If workspace_id is None, ALL claims on the bead are removed (used when
    a bead is closed/deleted, since any workspace's claim becomes stale).
    """
    server_db = db_infra.get_manager("server")
    async with server_db.transaction() as tx:
        # Find affected workspaces before deleting.
        if workspace_id:
            affected_ws_ids = [UUID(workspace_id)]
            await tx.execute(
                """
                DELETE FROM {{tables.bead_claims}}
                WHERE project_id = $1 AND workspace_id = $2 AND bead_id = $3
                """,
                UUID(project_id),
                UUID(workspace_id),
                bead_id,
            )
        else:
            rows = await tx.fetch_all(
                """
                DELETE FROM {{tables.bead_claims}}
                WHERE project_id = $1 AND bead_id = $2
                RETURNING workspace_id
                """,
                UUID(project_id),
                bead_id,
            )
            affected_ws_ids = [row["workspace_id"] for row in rows]

        # Update each affected workspace's focus to its next active claim.
        for ws_id in affected_ws_ids:
            next_claim = await tx.fetch_one(
                """
                SELECT apex_bead_id, apex_repo_name, apex_branch
                FROM {{tables.bead_claims}}
                WHERE project_id = $1 AND workspace_id = $2
                ORDER BY claimed_at DESC
                LIMIT 1
                """,
                UUID(project_id),
                ws_id,
            )
            await tx.execute(
                """
                UPDATE {{tables.workspaces}}
                SET focus_apex_bead_id = $1,
                    focus_apex_repo_name = $2,
                    focus_apex_branch = $3,
                    focus_updated_at = NOW(),
                    updated_at = NOW()
                WHERE project_id = $4 AND workspace_id = $5
                """,
                next_claim["apex_bead_id"] if next_claim else None,
                next_claim["apex_repo_name"] if next_claim else None,
                next_claim["apex_branch"] if next_claim else None,
                UUID(project_id),
                ws_id,
            )
