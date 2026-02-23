from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from aweb.auth import parse_bearer_token, verify_bearer_token_details
from fastapi import HTTPException, Request


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
    lifetime: str = "persistent"
    status: str = "active"


async def resolve_aweb_identity(request: Request, db) -> AwebIdentity:
    """Resolve the caller's aweb identity context.

    BeadHub implements the aweb protocol and owns the aweb schema.
    """
    token = parse_bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    details = await verify_bearer_token_details(db, token, manager_name="aweb")
    project_id = (details.get("project_id") or "").strip()
    agent_id = (details.get("agent_id") or "").strip()
    if not project_id or not agent_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    aweb_db = db.get_manager("aweb")
    agent = await aweb_db.fetch_one(
        """
        SELECT alias, human_name, did, custody, lifetime, status
        FROM {{tables.agents}}
        WHERE agent_id = $1 AND deleted_at IS NULL
        """,
        UUID(agent_id),
    )
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")

    project = await aweb_db.fetch_one(
        """
        SELECT slug, name
        FROM {{tables.projects}}
        WHERE project_id = $1 AND deleted_at IS NULL
        """,
        UUID(project_id),
    )
    if not project:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return AwebIdentity(
        project_id=project_id,
        project_slug=project["slug"],
        project_name=project.get("name") or "",
        agent_id=agent_id,
        alias=agent["alias"],
        human_name=agent.get("human_name") or "",
        did=agent.get("did"),
        custody=agent.get("custody"),
        lifetime=agent.get("lifetime") or "persistent",
        status=agent.get("status") or "active",
    )
