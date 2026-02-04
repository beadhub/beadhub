"""bdh coordination endpoints.

These endpoints are used by the `bdh` CLI wrapper to:
- preflight/record command execution (`POST /v1/bdh/command`)
- upload beads issue updates (`POST /v1/bdh/sync`)

They are intentionally thin wrappers around existing BeadHub primitives:
- auth comes from embedded aweb (`aw_sk_*` keys)
- bead sync uses `beadhub.beads_sync`
- notifications use the outbox pipeline in `beadhub.notifications`
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis

from beadhub.aweb_context import resolve_aweb_identity
from beadhub.aweb_introspection import get_identity_from_auth
from beadhub.auth import validate_workspace_id
from beadhub.beads_sync import (
    DEFAULT_BRANCH,
    BeadsSyncResult,
    _sync_issues_to_db,
    delete_issues_by_id,
    is_valid_alias,
    is_valid_canonical_origin,
    is_valid_human_name,
    validate_issues_from_list,
)
from beadhub.routes.repos import canonicalize_git_url, extract_repo_name
from ..db import DatabaseInfra, get_db_infra
from ..presence import get_workspace_id_by_alias
from ..jsonl import JSONLParseError, parse_jsonl
from ..notifications import process_notification_outbox, record_notification_intents
from ..redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/bdh", tags=["bdh"])

MAX_JSONL_SIZE = 10 * 1024 * 1024  # 10MB
MAX_ISSUES_COUNT = 10000
MAX_JSON_DEPTH = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_command_line(command_line: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (command, bead_id, status) best-effort, or (None, None, None)."""

    parts = command_line.split()
    if not parts:
        return None, None, None
    cmd = parts[0].strip()
    bead_id: Optional[str] = None
    status: Optional[str] = None
    if cmd in ("update", "close", "delete", "reopen") and len(parts) >= 2:
        bead_id = parts[1].strip()

    if cmd == "update":
        # Handle: --status in_progress OR --status=in_progress
        for i, p in enumerate(parts):
            if p == "--status" and i + 1 < len(parts):
                status = parts[i + 1].strip()
                break
            if p.startswith("--status="):
                status = p.split("=", 1)[1].strip()
                break

    return cmd, bead_id, status


async def _ensure_workspace_alive_or_410(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    server_db = db_infra.get_manager("server")
    row = await server_db.fetch_one(
        """
        SELECT workspace_id, alias, human_name, role, deleted_at
        FROM {{tables.workspaces}}
        WHERE workspace_id = $1 AND project_id = $2
        """,
        UUID(workspace_id),
        UUID(project_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if row.get("deleted_at") is not None:
        raise HTTPException(status_code=410, detail="Workspace was deleted")
    return row


async def _touch_workspace_last_seen(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
    human_name: str,
    role: Optional[str],
) -> None:
    server_db = db_infra.get_manager("server")
    await server_db.execute(
        """
        UPDATE {{tables.workspaces}}
        SET last_seen_at = $3,
            human_name = $4,
            role = $5
        WHERE workspace_id = $1 AND project_id = $2 AND deleted_at IS NULL
        """,
        UUID(workspace_id),
        UUID(project_id),
        _now(),
        human_name,
        role,
    )


async def _list_beads_in_progress(db_infra: DatabaseInfra, *, project_id: str) -> list[dict[str, Any]]:
    server_db = db_infra.get_manager("server")
    rows = await server_db.fetch_all(
        """
        SELECT bead_id, workspace_id, alias, human_name, claimed_at
        FROM {{tables.bead_claims}}
        WHERE project_id = $1
        ORDER BY claimed_at DESC
        LIMIT 200
        """,
        UUID(project_id),
    )
    return [
        {
            "bead_id": r["bead_id"],
            "workspace_id": str(r["workspace_id"]),
            "alias": r["alias"],
            "human_name": r["human_name"],
            "started_at": r["claimed_at"].isoformat(),
            "title": None,
            "role": None,
        }
        for r in rows
    ]


async def _upsert_claim(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
    alias: str,
    human_name: str,
    bead_id: str,
) -> None:
    server_db = db_infra.get_manager("server")
    await server_db.execute(
        """
        INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id, claimed_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (project_id, bead_id, workspace_id)
        DO UPDATE SET alias = EXCLUDED.alias, human_name = EXCLUDED.human_name, claimed_at = EXCLUDED.claimed_at
        """,
        UUID(project_id),
        UUID(workspace_id),
        alias,
        human_name,
        bead_id,
        _now(),
    )


async def _delete_claim(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
    bead_id: str,
) -> None:
    server_db = db_infra.get_manager("server")
    await server_db.execute(
        """
        DELETE FROM {{tables.bead_claims}}
        WHERE project_id = $1 AND workspace_id = $2 AND bead_id = $3
        """,
        UUID(project_id),
        UUID(workspace_id),
        bead_id,
    )


async def ensure_repo(
    db: DatabaseInfra,
    project_id: UUID,
    origin_url: str,
) -> UUID:
    """Ensure a repo exists for the given project and origin.

    Returns the repo_id (existing or newly created).
    """
    canonical_origin = canonicalize_git_url(origin_url)
    repo_name = extract_repo_name(canonical_origin)

    server_db = db.get_manager("server")
    # Also clear deleted_at to undelete soft-deleted repos when re-registered
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
    """Upsert workspace into persistent workspaces table.

    Creates or updates the workspace record. The workspace_id is the constant
    identifier. project_id, repo_id, alias, hostname, and workspace_path are
    immutable after creation (hostname/workspace_path can be set once if NULL).
    Only human_name, role, current_branch, deleted_at, and last_seen_at can be updated.

    last_seen_at is updated on every bdh command to track workspace activity.
    """
    server_db = db.get_manager("server")
    await server_db.execute(
        """
        INSERT INTO {{tables.workspaces}} (workspace_id, project_id, repo_id, alias, human_name, role, hostname, workspace_path, last_seen_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        ON CONFLICT (workspace_id) DO UPDATE SET
            human_name = EXCLUDED.human_name,
            role = COALESCE(EXCLUDED.role, {{tables.workspaces}}.role),
            hostname = COALESCE({{tables.workspaces}}.hostname, EXCLUDED.hostname),
            workspace_path = COALESCE({{tables.workspaces}}.workspace_path, EXCLUDED.workspace_path),
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
    """Check if alias is already used by another workspace within the same project.

    Aliases are unique per project (not globally). Projects are tenant boundaries
    with no cross-project communication, so per-project uniqueness is sufficient.

    Returns:
        The workspace_id using this alias if collision, None if available.
    """
    server_db = db.get_manager("server")

    # Check workspaces table first (authoritative source)
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

    # Also check bead_claims for another workspace with same alias
    # (handles race conditions before workspace is persisted)
    row = await server_db.fetch_one(
        """
        SELECT DISTINCT workspace_id
        FROM {{tables.bead_claims}}
        WHERE project_id = $1 AND alias = $2 AND workspace_id != $3
        LIMIT 1
        """,
        project_id,
        alias,
        UUID(workspace_id),
    )
    if row:
        return str(row["workspace_id"])

    # Check Redis presence for another workspace with same alias
    # Uses O(1) secondary index instead of SCAN
    colliding_workspace = await get_workspace_id_by_alias(redis, str(project_id), alias)
    if colliding_workspace and colliding_workspace != workspace_id:
        return colliding_workspace

    return None


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(..., min_length=1)
    repo_id: str | None = None
    alias: str = Field(..., min_length=1, max_length=64)
    human_name: str = Field(..., min_length=0, max_length=64)
    repo_origin: str = Field(..., min_length=1, max_length=2048)
    role: str | None = Field(default=None, max_length=50)
    command_line: str = Field(..., min_length=1, max_length=8192)

    @field_validator("workspace_id")
    @classmethod
    def _validate_workspace_id(cls, v: str) -> str:
        return validate_workspace_id(v)

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str) -> str:
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


class CommandContext(BaseModel):
    messages_waiting: int = 0
    beads_in_progress: list[dict[str, Any]] = Field(default_factory=list)


class CommandResponse(BaseModel):
    approved: bool
    reason: str = ""
    context: CommandContext | None = None


@router.post("/command", response_model=CommandResponse)
async def command(
    request: Request,
    payload: CommandRequest,
    db_infra: DatabaseInfra = Depends(get_db_infra),
) -> CommandResponse:
    identity = await get_identity_from_auth(request, db_infra)
    project_id = identity.project_id

    # If auth provides an agent identity, it must match the claimed workspace_id.
    if identity.agent_id is not None and identity.agent_id != payload.workspace_id:
        raise HTTPException(status_code=403, detail="workspace_id does not match API key identity")

    # Ensure workspace exists, belongs to project, and is not deleted (410).
    await _ensure_workspace_alive_or_410(
        db_infra, project_id=project_id, workspace_id=payload.workspace_id
    )

    await _touch_workspace_last_seen(
        db_infra,
        project_id=project_id,
        workspace_id=payload.workspace_id,
        human_name=payload.human_name or "",
        role=payload.role,
    )

    beads_in_progress = await _list_beads_in_progress(db_infra, project_id=project_id)
    return CommandResponse(
        approved=True,
        context=CommandContext(messages_waiting=0, beads_in_progress=beads_in_progress),
    )


class SyncStats(BaseModel):
    received: int = 0
    inserted: int = 0
    updated: int = 0
    deleted: int = 0


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(..., min_length=1)
    repo_id: str | None = None
    alias: str = Field(..., min_length=1, max_length=64)
    human_name: str = Field(..., min_length=0, max_length=64)
    repo_origin: str = Field(..., min_length=1, max_length=2048)
    role: str | None = Field(default=None, max_length=50)

    # Full sync mode
    issues_jsonl: str | None = Field(default=None, max_length=MAX_JSONL_SIZE)

    # Incremental sync mode
    sync_mode: str | None = Field(default=None, max_length=32)
    changed_issues: str | None = Field(default=None, max_length=MAX_JSONL_SIZE)
    deleted_ids: list[str] = Field(default_factory=list)
    sync_protocol_version: int | None = None

    # Command context for claim attribution (best-effort)
    command_line: str | None = Field(default=None, max_length=8192)

    @field_validator("workspace_id")
    @classmethod
    def _validate_workspace_id(cls, v: str) -> str:
        return validate_workspace_id(v)

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str) -> str:
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


class SyncResponse(BaseModel):
    synced: bool = True
    issues_count: int = 0
    context: CommandContext | None = None
    stats: SyncStats | None = None
    sync_protocol_version: int = 1


@router.post("/sync", response_model=SyncResponse)
async def sync(
    request: Request,
    payload: SyncRequest,
    db_infra: DatabaseInfra = Depends(get_db_infra),
    redis: Redis = Depends(get_redis),
) -> SyncResponse:
    identity = await get_identity_from_auth(request, db_infra)
    project_id = identity.project_id

    if identity.agent_id is not None and identity.agent_id != payload.workspace_id:
        raise HTTPException(status_code=403, detail="workspace_id does not match API key identity")

    await _ensure_workspace_alive_or_410(
        db_infra, project_id=project_id, workspace_id=payload.workspace_id
    )

    # Touch workspace activity for "gone workspace" and status displays.
    await _touch_workspace_last_seen(
        db_infra,
        project_id=project_id,
        workspace_id=payload.workspace_id,
        human_name=payload.human_name or "",
        role=payload.role,
    )

    canonical_origin = canonicalize_git_url(payload.repo_origin)
    if not is_valid_canonical_origin(canonical_origin):
        raise HTTPException(status_code=422, detail="Invalid repo_origin")

    beads_db = db_infra.get_manager("beads")

    mode = (payload.sync_mode or "full").strip().lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=422, detail="sync_mode must be 'full' or 'incremental'")

    received = 0
    inserted = 0
    updated = 0
    deleted = 0

    result: Optional[BeadsSyncResult] = None
    if mode == "full":
        body = (payload.issues_jsonl or "").strip()
        if not body:
            raise HTTPException(status_code=422, detail="issues_jsonl is required for full sync")
        try:
            issues_raw = parse_jsonl(body, max_depth=MAX_JSON_DEPTH, max_count=MAX_ISSUES_COUNT)
        except JSONLParseError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        issues = validate_issues_from_list(issues_raw)
        received = len(issues)
        result = await _sync_issues_to_db(
            issues,
            beads_db,
            project_id=project_id,
            repo=canonical_origin,
            branch=DEFAULT_BRANCH,
        )
        inserted = result.issues_added
        updated = result.issues_updated
    else:
        if (payload.changed_issues is None or payload.changed_issues.strip() == "") and not payload.deleted_ids:
            raise HTTPException(status_code=422, detail="incremental sync requires changes or deletions")

        if payload.changed_issues is not None and payload.changed_issues.strip():
            try:
                issues_raw = parse_jsonl(
                    payload.changed_issues, max_depth=MAX_JSON_DEPTH, max_count=MAX_ISSUES_COUNT
                )
            except JSONLParseError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            issues = validate_issues_from_list(issues_raw)
            received = len(issues)
            result = await _sync_issues_to_db(
                issues,
                beads_db,
                project_id=project_id,
                repo=canonical_origin,
                branch=DEFAULT_BRANCH,
            )
            inserted = result.issues_added
            updated = result.issues_updated

        if payload.deleted_ids:
            deleted = await delete_issues_by_id(
                beads_db,
                project_id=project_id,
                bead_ids=payload.deleted_ids,
                repo=canonical_origin,
                branch=DEFAULT_BRANCH,
            )

    # Update claims based on the bd command that succeeded (best-effort).
    cmd, bead_id, status = _parse_command_line(payload.command_line or "")
    if bead_id:
        if cmd == "update" and status == "in_progress":
            await _upsert_claim(
                db_infra,
                project_id=project_id,
                workspace_id=payload.workspace_id,
                alias=payload.alias,
                human_name=payload.human_name or "",
                bead_id=bead_id,
            )
        elif cmd in ("close", "delete") or (cmd == "update" and status and status != "in_progress"):
            await _delete_claim(
                db_infra,
                project_id=project_id,
                workspace_id=payload.workspace_id,
                bead_id=bead_id,
            )

    if payload.deleted_ids:
        # Ensure deletions also remove claims for this workspace.
        for bid in payload.deleted_ids:
            await _delete_claim(
                db_infra,
                project_id=project_id,
                workspace_id=payload.workspace_id,
                bead_id=bid,
            )

    # Record notification intents in outbox, then process them.
    notifications_sent = 0
    notifications_failed = 0
    if result is not None and result.status_changes:
        await record_notification_intents(result.status_changes, project_id, db_infra)
        sender = await resolve_aweb_identity(request, db_infra)
        notifications_sent, notifications_failed = await process_notification_outbox(
            project_id,
            db_infra,
            sender_agent_id=sender.agent_id,
            sender_alias=sender.alias,
        )

    # Update audit log (best-effort; don't fail the sync on logging issues).
    try:
        server_db = db_infra.get_manager("server")
        await server_db.execute(
            """
            INSERT INTO {{tables.audit_log}} (project_id, event_type, details)
            VALUES ($1, $2, $3::jsonb)
            """,
            UUID(project_id),
            "bdh_sync",
            json.dumps(
                {
                    "project_id": project_id,
                    "repo": canonical_origin,
                    "mode": mode,
                    "received": received,
                    "inserted": inserted,
                    "updated": updated,
                    "deleted": deleted,
                    "notifications_sent": notifications_sent,
                    "notifications_failed": notifications_failed,
                }
            ),
        )
    except Exception:
        logger.exception("Failed to write audit log for bdh sync")

    # Count total issues for this (project, repo, branch) after sync.
    count_row = await beads_db.fetch_one(
        """
        SELECT COUNT(*) AS c
        FROM {{tables.beads_issues}}
        WHERE project_id = $1 AND repo = $2 AND branch = $3
        """,
        UUID(project_id),
        canonical_origin,
        DEFAULT_BRANCH,
    )
    issues_count = int(count_row["c"]) if count_row else 0

    return SyncResponse(
        synced=True,
        issues_count=issues_count,
        stats=SyncStats(received=received, inserted=inserted, updated=updated, deleted=deleted),
        sync_protocol_version=1,
    )
