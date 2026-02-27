from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

from ..aweb_introspection import get_project_from_auth
from ..config import get_settings
from ..db import DatabaseInfra, get_db_infra
from ..events import ChatMessageEvent, publish_event
from ..redis_client import get_redis

router = APIRouter(prefix="/v1", tags=["dashboard"])


# ── Dashboard Config & Identity ──────────────────────────────────────────────


class DashboardConfigResponse(BaseModel):
    human_name: str


@router.get("/dashboard/config", response_model=DashboardConfigResponse)
async def get_dashboard_config(request: Request):
    """Return dashboard configuration (human_name from env var)."""
    settings = get_settings()
    return DashboardConfigResponse(human_name=settings.dashboard_human)


class DashboardIdentityRequest(BaseModel):
    human_name: str
    alias: str | None = None


class DashboardIdentityResponse(BaseModel):
    workspace_id: str
    alias: str
    human_name: str
    workspace_type: str


@router.post("/dashboard/identity", response_model=DashboardIdentityResponse)
async def get_or_create_dashboard_identity(
    body: DashboardIdentityRequest,
    request: Request,
    db_infra: DatabaseInfra = Depends(get_db_infra),
):
    """Get or create a dashboard workspace for the human user."""
    project_id = await get_project_from_auth(request, db_infra)
    server_db = db_infra.get_manager("server")

    row = await server_db.fetch_one(
        """
        SELECT workspace_id, alias, human_name, workspace_type
        FROM {{tables.workspaces}}
        WHERE project_id = $1
          AND workspace_type = 'dashboard'
          AND deleted_at IS NULL
        ORDER BY created_at ASC
        LIMIT 1
        """,
        project_id,
    )

    if row:
        return DashboardIdentityResponse(
            workspace_id=str(row["workspace_id"]),
            alias=row["alias"],
            human_name=row["human_name"],
            workspace_type=row["workspace_type"],
        )

    workspace_id = str(uuid4())
    alias = body.alias or f"dashboard-{body.human_name}"
    now = datetime.now(timezone.utc)

    await server_db.execute(
        """
        INSERT INTO {{tables.workspaces}}
            (workspace_id, project_id, alias, human_name, workspace_type, role, created_at, updated_at)
        VALUES ($1, $2, $3, $4, 'dashboard', 'human', $5, $5)
        """,
        workspace_id,
        project_id,
        alias,
        body.human_name,
        now,
    )

    return DashboardIdentityResponse(
        workspace_id=workspace_id,
        alias=alias,
        human_name=body.human_name,
        workspace_type="dashboard",
    )


# ── Chat Admin (project-wide monitoring for dashboard) ───────────────────────


def _utc_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class AdminSessionParticipant(BaseModel):
    workspace_id: str
    alias: str


class AdminSessionListItem(BaseModel):
    session_id: str
    participants: list[AdminSessionParticipant]
    last_message: str | None = None
    last_from: str | None = None
    last_activity: str | None = None
    message_count: int = 0


class AdminSessionListResponse(BaseModel):
    sessions: list[AdminSessionListItem]
    has_more: bool = False
    next_cursor: str | None = None


@router.get("/chat/admin/sessions", response_model=AdminSessionListResponse)
async def list_all_sessions(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    db_infra: DatabaseInfra = Depends(get_db_infra),
):
    """List all chat sessions in the project (admin/dashboard view)."""
    project_id = await get_project_from_auth(request, db_infra)
    aweb_db = db_infra.get_manager("aweb")

    rows = await aweb_db.fetch_all(
        """
        SELECT s.session_id, s.created_at
        FROM {{tables.chat_sessions}} s
        WHERE s.project_id = $1
        ORDER BY s.created_at DESC
        LIMIT $2
        """,
        UUID(project_id),
        limit + 1,
    )

    has_more = len(rows) > limit
    rows = rows[:limit]

    sessions = []
    for row in rows:
        session_id = row["session_id"]

        # Get participants with their workspace_id
        participant_rows = await aweb_db.fetch_all(
            """
            SELECT p.agent_id, p.alias
            FROM {{tables.chat_session_participants}} p
            WHERE p.session_id = $1
            ORDER BY p.alias ASC
            """,
            session_id,
        )
        participants = [
            AdminSessionParticipant(
                workspace_id=str(p["agent_id"]),
                alias=p["alias"],
            )
            for p in participant_rows
        ]

        # Get last message and count
        msg_row = await aweb_db.fetch_one(
            """
            SELECT body, from_alias, created_at, count(*) OVER() as total_count
            FROM {{tables.chat_messages}}
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            session_id,
        )

        last_message = None
        last_from = None
        last_activity = _utc_iso(row["created_at"])
        message_count = 0

        if msg_row:
            last_message = msg_row["body"][:200] if msg_row["body"] else None
            last_from = msg_row["from_alias"]
            last_activity = _utc_iso(msg_row["created_at"])
            message_count = msg_row["total_count"]

        sessions.append(
            AdminSessionListItem(
                session_id=str(session_id),
                participants=participants,
                last_message=last_message,
                last_from=last_from,
                last_activity=last_activity,
                message_count=message_count,
            )
        )

    return AdminSessionListResponse(
        sessions=sessions,
        has_more=has_more,
        next_cursor=str(rows[-1]["session_id"]) if has_more and rows else None,
    )


class AdminMessageItem(BaseModel):
    message_id: str
    from_agent: str
    body: str
    created_at: str


class AdminMessageHistoryResponse(BaseModel):
    session_id: str
    messages: list[AdminMessageItem]


@router.get(
    "/chat/admin/sessions/{session_id}/messages",
    response_model=AdminMessageHistoryResponse,
)
async def get_session_messages_admin(
    request: Request,
    session_id: str = Path(..., min_length=1),
    workspace_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    db_infra: DatabaseInfra = Depends(get_db_infra),
):
    """Get messages for a chat session (admin view, no participant check)."""
    project_id = await get_project_from_auth(request, db_infra)
    aweb_db = db_infra.get_manager("aweb")

    try:
        session_uuid = UUID(session_id.strip())
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid session_id format")

    # Verify session belongs to project
    sess = await aweb_db.fetch_one(
        "SELECT 1 FROM {{tables.chat_sessions}} WHERE session_id = $1 AND project_id = $2",
        session_uuid,
        UUID(project_id),
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = await aweb_db.fetch_all(
        """
        SELECT message_id, from_alias, body, created_at
        FROM {{tables.chat_messages}}
        WHERE session_id = $1
        ORDER BY created_at ASC
        LIMIT $2
        """,
        session_uuid,
        limit,
    )

    messages = [
        AdminMessageItem(
            message_id=str(r["message_id"]),
            from_agent=r["from_alias"],
            body=r["body"],
            created_at=_utc_iso(r["created_at"]),
        )
        for r in rows
    ]

    return AdminMessageHistoryResponse(
        session_id=session_id,
        messages=messages,
    )


class JoinSessionRequest(BaseModel):
    workspace_id: str
    alias: str


class JoinSessionResponse(BaseModel):
    session_id: str
    workspace_id: str
    alias: str
    joined_at: str


@router.post(
    "/chat/admin/sessions/{session_id}/join",
    response_model=JoinSessionResponse,
)
async def join_session(
    request: Request,
    body: JoinSessionRequest,
    session_id: str = Path(..., min_length=1),
    db_infra: DatabaseInfra = Depends(get_db_infra),
):
    """Join a chat session as a dashboard user (admin)."""
    project_id = await get_project_from_auth(request, db_infra)
    aweb_db = db_infra.get_manager("aweb")

    try:
        session_uuid = UUID(session_id.strip())
        workspace_uuid = UUID(body.workspace_id.strip())
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid UUID format")

    # Verify session belongs to project
    sess = await aweb_db.fetch_one(
        "SELECT 1 FROM {{tables.chat_sessions}} WHERE session_id = $1 AND project_id = $2",
        session_uuid,
        UUID(project_id),
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if already a participant
    existing = await aweb_db.fetch_one(
        "SELECT 1 FROM {{tables.chat_session_participants}} WHERE session_id = $1 AND agent_id = $2",
        session_uuid,
        workspace_uuid,
    )

    now = datetime.now(timezone.utc)

    if not existing:
        # Ensure the dashboard workspace exists in the aweb agents table
        # (chat_session_participants has a FK to agents)
        agent_exists = await aweb_db.fetch_one(
            "SELECT 1 FROM {{tables.agents}} WHERE agent_id = $1",
            workspace_uuid,
        )
        if not agent_exists:
            await aweb_db.execute(
                """
                INSERT INTO {{tables.agents}}
                    (agent_id, project_id, alias, agent_type, lifetime, created_at)
                VALUES ($1, $2, $3, 'dashboard', 'persistent', $4)
                """,
                workspace_uuid,
                UUID(project_id),
                body.alias,
                now,
            )

        await aweb_db.execute(
            """
            INSERT INTO {{tables.chat_session_participants}}
                (session_id, agent_id, alias, joined_at)
            VALUES ($1, $2, $3, $4)
            """,
            session_uuid,
            workspace_uuid,
            body.alias,
            now,
        )

    return JoinSessionResponse(
        session_id=session_id,
        workspace_id=body.workspace_id,
        alias=body.alias,
        joined_at=_utc_iso(now),
    )


# ── Chat session create (dashboard override) ─────────────────────────────────
# The frontend sends { from_workspace, from_alias, to_aliases, message } but
# the aweb route only accepts { to_aliases, message } (extra="forbid").
# This override accepts the dashboard fields and creates the session directly.


class DashboardStartChatRequest(BaseModel):
    to_aliases: list[str]
    message: str = Field(..., min_length=1)
    from_workspace: str | None = None
    from_alias: str | None = None


class DashboardStartChatParticipant(BaseModel):
    workspace_id: str
    alias: str


class DashboardStartChatResponse(BaseModel):
    session_id: str
    message_id: str
    participants: list[DashboardStartChatParticipant]


@router.post("/chat/sessions", response_model=DashboardStartChatResponse)
async def start_chat_session(
    request: Request,
    payload: DashboardStartChatRequest,
    db_infra: DatabaseInfra = Depends(get_db_infra),
    redis=Depends(get_redis),
):
    """Create a chat session, accepting dashboard fields (from_workspace, from_alias)."""
    project_id = await get_project_from_auth(request, db_infra)
    aweb_db = db_infra.get_manager("aweb")

    # Determine sender identity
    if payload.from_workspace:
        sender_id = UUID(payload.from_workspace.strip())
        sender_alias = payload.from_alias or "unknown"
    else:
        from ..aweb_introspection import get_identity_from_auth

        identity = await get_identity_from_auth(request, db_infra)
        sender_id = UUID(identity.agent_id) if identity.agent_id else None
        if not sender_id:
            raise HTTPException(status_code=400, detail="Cannot determine sender")
        row = await aweb_db.fetch_one(
            "SELECT alias FROM {{tables.agents}} WHERE agent_id = $1",
            sender_id,
        )
        sender_alias = row["alias"] if row else "unknown"

    # Ensure sender exists in agents table
    agent_exists = await aweb_db.fetch_one(
        "SELECT 1 FROM {{tables.agents}} WHERE agent_id = $1",
        sender_id,
    )
    if not agent_exists:
        now_ts = datetime.now(timezone.utc)
        await aweb_db.execute(
            """
            INSERT INTO {{tables.agents}}
                (agent_id, project_id, alias, agent_type, lifetime, created_at)
            VALUES ($1, $2, $3, 'dashboard', 'persistent', $4)
            """,
            sender_id,
            UUID(project_id),
            sender_alias,
            now_ts,
        )

    # Resolve target aliases to agent IDs
    participants: list[DashboardStartChatParticipant] = [
        DashboardStartChatParticipant(workspace_id=str(sender_id), alias=sender_alias)
    ]

    target_agents = []
    for alias in payload.to_aliases:
        row = await aweb_db.fetch_one(
            "SELECT agent_id, alias FROM {{tables.agents}} WHERE project_id = $1 AND alias = $2",
            UUID(project_id),
            alias,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Agent '{alias}' not found")
        target_agents.append(row)
        participants.append(
            DashboardStartChatParticipant(
                workspace_id=str(row["agent_id"]), alias=row["alias"]
            )
        )

    # Build participant hash (sorted aliases) to deduplicate sessions
    all_aliases = sorted(p.alias for p in participants)
    participant_hash = hashlib.sha256(":".join(all_aliases).encode()).hexdigest()

    message_id = uuid4()
    now = datetime.now(timezone.utc)

    # Reuse existing session if same participants already have one
    existing = await aweb_db.fetch_one(
        """
        SELECT session_id FROM {{tables.chat_sessions}}
        WHERE project_id = $1 AND participant_hash = $2
        """,
        UUID(project_id),
        participant_hash,
    )

    if existing:
        session_id = existing["session_id"]
    else:
        session_id = uuid4()
        await aweb_db.execute(
            """
            INSERT INTO {{tables.chat_sessions}}
                (session_id, project_id, participant_hash, created_at)
            VALUES ($1, $2, $3, $4)
            """,
            session_id,
            UUID(project_id),
            participant_hash,
            now,
        )

        # Add all participants
        for p in participants:
            await aweb_db.execute(
                """
                INSERT INTO {{tables.chat_session_participants}}
                    (session_id, agent_id, alias, joined_at)
                VALUES ($1, $2, $3, $4)
                """,
                session_id,
                UUID(p.workspace_id),
                p.alias,
                now,
            )

    # Insert the initial message
    await aweb_db.execute(
        """
        INSERT INTO {{tables.chat_messages}}
            (message_id, session_id, from_agent_id, from_alias, body, created_at, sender_leaving)
        VALUES ($1, $2, $3, $4, $5, $6, false)
        """,
        message_id,
        session_id,
        sender_id,
        sender_alias,
        payload.message,
        now,
    )

    # Publish event so Redis subscribers (discord-bridge, SSE) see it
    to_aliases = [p.alias for p in participants if p.alias != sender_alias]
    event = ChatMessageEvent(
        workspace_id=str(sender_id),
        session_id=str(session_id),
        message_id=str(message_id),
        from_alias=sender_alias,
        to_aliases=to_aliases,
        preview=payload.message[:80],
        project_id=project_id,
    )
    await publish_event(redis, event)

    return DashboardStartChatResponse(
        session_id=str(session_id),
        message_id=str(message_id),
        participants=participants,
    )


# ── Chat message send (dashboard override) ──────────────────────────────────
# The frontend sends { workspace_id, alias, body } but the aweb route only
# accepts { body } (extra="forbid"). This override accepts the dashboard
# fields and inserts the message directly.


class DashboardChatMessageRequest(BaseModel):
    body: str = Field(..., min_length=1)
    workspace_id: str | None = None
    alias: str | None = None


class DashboardChatMessageResponse(BaseModel):
    message_id: str
    delivered: bool


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=DashboardChatMessageResponse,
)
async def send_chat_message(
    request: Request,
    payload: DashboardChatMessageRequest,
    session_id: str = Path(..., min_length=1),
    db_infra: DatabaseInfra = Depends(get_db_infra),
    redis=Depends(get_redis),
):
    """Send a chat message, accepting dashboard fields (workspace_id, alias)."""
    project_id = await get_project_from_auth(request, db_infra)
    aweb_db = db_infra.get_manager("aweb")

    try:
        session_uuid = UUID(session_id.strip())
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid session_id format")

    # Verify session belongs to project
    sess = await aweb_db.fetch_one(
        "SELECT 1 FROM {{tables.chat_sessions}} WHERE session_id = $1 AND project_id = $2",
        session_uuid,
        UUID(project_id),
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine sender: use workspace_id/alias from payload if provided,
    # otherwise fall back to auth identity
    if payload.workspace_id:
        sender_id = UUID(payload.workspace_id.strip())
        sender_alias = payload.alias or "unknown"
    else:
        from ..aweb_introspection import get_identity_from_auth

        identity = await get_identity_from_auth(request, db_infra)
        sender_id = UUID(identity.agent_id) if identity.agent_id else None
        if not sender_id:
            raise HTTPException(status_code=400, detail="Cannot determine sender")
        # Look up alias
        row = await aweb_db.fetch_one(
            "SELECT alias FROM {{tables.agents}} WHERE agent_id = $1",
            sender_id,
        )
        sender_alias = row["alias"] if row else "unknown"

    # Verify sender is a participant
    participant = await aweb_db.fetch_one(
        "SELECT 1 FROM {{tables.chat_session_participants}} WHERE session_id = $1 AND agent_id = $2",
        session_uuid,
        sender_id,
    )
    if not participant:
        raise HTTPException(status_code=403, detail="Not a participant in this session")

    message_id = uuid4()
    now = datetime.now(timezone.utc)

    await aweb_db.execute(
        """
        INSERT INTO {{tables.chat_messages}}
            (message_id, session_id, from_agent_id, from_alias, body, created_at, sender_leaving)
        VALUES ($1, $2, $3, $4, $5, $6, false)
        """,
        message_id,
        session_uuid,
        sender_id,
        sender_alias,
        payload.body,
        now,
    )

    # Publish event so Redis subscribers (discord-bridge, SSE) see it
    other_aliases = [
        r["alias"]
        for r in await aweb_db.fetch_all(
            "SELECT alias FROM {{tables.chat_session_participants}} WHERE session_id = $1 AND agent_id != $2",
            session_uuid,
            sender_id,
        )
    ]
    event = ChatMessageEvent(
        workspace_id=str(sender_id),
        session_id=str(session_uuid),
        message_id=str(message_id),
        from_alias=sender_alias,
        to_aliases=other_aliases,
        preview=payload.body[:80],
        project_id=project_id,
    )
    await publish_event(redis, event)

    return DashboardChatMessageResponse(
        message_id=str(message_id),
        delivered=True,
    )
