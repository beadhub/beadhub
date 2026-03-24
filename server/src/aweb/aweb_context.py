from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request

from .auth import parse_bearer_token, verify_bearer_token_details
from .aweb_introspection import get_identity_from_auth
from .scope_agents import get_scope_agent
from .projection import ensure_aweb_project_and_agent


@dataclass(frozen=True)
class AwebIdentity:
    project_id: str
    project_slug: str
    project_name: str
    agent_id: str
    alias: str
    human_name: str
    did: str | None = None
    custody: str | None = None
    lifetime: str = "ephemeral"
    status: str = "active"


async def resolve_aweb_identity(request: Request, db) -> AwebIdentity:
    """Resolve the caller's aweb identity context.

    Coordination identity is canonical in the embedded protocol core; aweb keeps
    only local projection data.
    """
    identity = await get_identity_from_auth(request, db)
    project_id = (identity.project_id or "").strip()
    agent_id = (identity.agent_id or "").strip() if identity.agent_id else ""
    if not project_id or not agent_id:
        token = parse_bearer_token(request)
        if token is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        details = await verify_bearer_token_details(db, token, manager_name="aweb")
        project_id = (details.get("project_id") or "").strip()
        agent_id = (details.get("agent_id") or "").strip()
        if not project_id or not agent_id:
            raise HTTPException(status_code=401, detail="Invalid API key")

    server_db = db.get_manager("server")
    project = await server_db.fetch_one(
        """
        SELECT id, slug, name
        FROM {{tables.projects}}
        WHERE id = $1 AND deleted_at IS NULL
        """,
        UUID(project_id),
    )
    if not project:
        raise HTTPException(status_code=401, detail="Invalid API key")
    agent = await get_scope_agent(
        aweb_db=db.get_manager("aweb"),
        scope_id=project_id,
        agent_ref=agent_id,
    )

    aweb_db = db.get_manager("aweb")
    await ensure_aweb_project_and_agent(
        oss_db=server_db,
        aweb_db=aweb_db,
        project_id=project_id,
        workspace_id=agent_id,
        alias=str(agent.get("alias") or ""),
        human_name=str(agent.get("human_name") or agent.get("alias") or ""),
        agent_type=str(agent.get("agent_type") or "agent"),
        role=str(agent.get("role") or "") or None,
        program=str(agent.get("program") or "") or None,
    )
    projection = await aweb_db.fetch_one(
        """
        SELECT alias, human_name
        FROM {{tables.agents}}
        WHERE agent_id = $1 AND project_id = $2 AND deleted_at IS NULL
        """,
        UUID(agent_id),
        UUID(project_id),
    )

    return AwebIdentity(
        project_id=project_id,
        project_slug=project["slug"],
        project_name=project.get("name") or "",
        agent_id=agent_id,
        alias=str((projection or {}).get("alias") or agent.get("alias") or ""),
        human_name=str((projection or {}).get("human_name") or agent.get("human_name") or ""),
        did=agent.get("did"),
        custody=agent.get("custody"),
        lifetime=agent.get("lifetime") or "ephemeral",
        status=agent.get("status") or "active",
    )
