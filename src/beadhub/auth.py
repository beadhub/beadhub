from __future__ import annotations

import uuid
from typing import Any, Optional, Protocol

from fastapi import HTTPException, Request

from beadhub.aweb_introspection import AuthIdentity, get_identity_from_auth


class DatabaseLike(Protocol):
    def get_manager(self, name: str = "server") -> Any: ...


def enforce_actor_binding(
    identity: AuthIdentity,
    workspace_id: str,
    detail: str = "workspace_id does not match API key identity",
) -> None:
    """Reject requests where the caller's API key identity doesn't match the workspace.

    In bearer mode (direct API key), agent_id is the workspace UUID and must match.
    In proxy mode (Cloud), actor_id is a Cloud service UUID — the Cloud wrapper
    handles actor binding, so this check is skipped.
    """
    if (
        identity.auth_mode == "bearer"
        and identity.agent_id is not None
        and identity.agent_id != workspace_id
    ):
        raise HTTPException(status_code=403, detail=detail)


def validate_workspace_id(workspace_id: str) -> str:
    """Validate workspace_id is a valid UUID string and return normalized format."""
    if workspace_id is None:
        raise ValueError("workspace_id cannot be empty")
    workspace_id = str(workspace_id).strip()
    if not workspace_id:
        raise ValueError("workspace_id cannot be empty")
    try:
        return str(uuid.UUID(workspace_id))
    except ValueError:
        raise ValueError("Invalid workspace_id format")


async def get_workspace_project_id(
    db: DatabaseLike,
    workspace_id: str,
) -> Optional[str]:
    """Return project_id for workspace_id or None if not found."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return None

    server_db = db.get_manager("server")
    row = await server_db.fetch_one(
        """
        SELECT project_id
        FROM {{tables.workspaces}}
        WHERE workspace_id = $1 AND deleted_at IS NULL
        """,
        ws_uuid,
    )
    if not row:
        return None
    return str(row["project_id"])


async def verify_workspace_access(
    request: Request,
    workspace_id: str,
    db: DatabaseLike,
) -> str:
    """Verify workspace_id belongs to the authenticated project, return project_id.

    This enforces the invariant documented in `security-patterns.md`:
    - project scope is derived from auth (API key or signed proxy context)
    - workspace_id is validated and must belong to that project
    - in direct Bearer mode, workspace-scoped operations MUST use the caller's identity
    """
    try:
        workspace_id = validate_workspace_id(workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    identity = await get_identity_from_auth(request, db)
    project_id = identity.project_id

    server_db = db.get_manager("server")
    row = await server_db.fetch_one(
        """
        SELECT project_id, deleted_at
        FROM {{tables.workspaces}}
        WHERE workspace_id = $1
        """,
        uuid.UUID(workspace_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if row.get("deleted_at") is not None:
        raise HTTPException(status_code=410, detail="Workspace was deleted")

    ws_project_id = str(row["project_id"])
    if ws_project_id != project_id:
        raise HTTPException(
            status_code=403,
            detail="Workspace not found or does not belong to your project",
        )

    # Enforced after existence checks so ghost workspaces still return 404/410.
    enforce_actor_binding(identity, workspace_id)

    return project_id
