from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from aweb.auth import parse_bearer_token, verify_bearer_token_details

from .db import DatabaseInfra
from .internal_auth import parse_internal_auth_context


@dataclass(frozen=True)
class AuthIdentity:
    project_id: str
    agent_id: str | None
    api_key_id: str | None
    user_id: str | None
    auth_mode: str  # "proxy" or "bearer"


async def get_identity_from_auth(request: Request, db: DatabaseInfra) -> AuthIdentity:
    """Resolve the authenticated identity context for BeadHub requests.

    Priority order:
    1) Trusted proxy/wrapper auth context (`X-BH-Auth` + `X-Project-ID`)
    2) Local aweb Bearer API key (default; BeadHub implements the aweb protocol)
    """
    internal = parse_internal_auth_context(request)
    if internal is not None:
        principal_type = (internal.get("principal_type") or "").strip()
        principal_id = (internal.get("principal_id") or "").strip() or None
        actor_id = (internal.get("actor_id") or "").strip() or None
        return AuthIdentity(
            project_id=internal["project_id"],
            agent_id=actor_id,
            api_key_id=principal_id if principal_type == "k" else None,
            user_id=principal_id if principal_type == "u" else None,
            auth_mode="proxy",
        )

    token = parse_bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    details = await verify_bearer_token_details(db, token, manager_name="aweb")
    project_id = (details.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    agent_id = (details.get("agent_id") or "").strip() or None
    api_key_id = (details.get("api_key_id") or "").strip() or None
    user_id = (details.get("user_id") or "").strip() or None
    return AuthIdentity(
        project_id=project_id,
        agent_id=agent_id,
        api_key_id=api_key_id,
        user_id=user_id,
        auth_mode="bearer",
    )


async def get_project_from_auth(request: Request, db: DatabaseInfra) -> str:
    """Resolve the authenticated project_id for BeadHub requests.

    Priority order:
    1) Trusted proxy/wrapper auth context (`X-BH-Auth` + `X-Project-ID`)
    2) Local aweb auth (default; BeadHub implements the aweb protocol)
    """
    # 1) Proxy headers (signed internal context)
    identity = await get_identity_from_auth(request, db)
    return identity.project_id
