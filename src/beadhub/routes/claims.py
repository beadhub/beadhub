"""Claims API - View active bead claims."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from beadhub.auth import validate_workspace_id
from beadhub.aweb_introspection import get_project_from_auth

from ..db import DatabaseInfra, get_db_infra
from ..pagination import encode_cursor, validate_pagination_params

router = APIRouter(prefix="/v1", tags=["claims"])


class Claim(BaseModel):
    """A bead claim - indicates a workspace is working on a bead."""

    bead_id: str
    workspace_id: str
    alias: str
    human_name: str
    claimed_at: str
    project_id: str


class ClaimsResponse(BaseModel):
    """Response for GET /v1/claims."""

    claims: List[Claim]
    has_more: bool = False
    next_cursor: Optional[str] = None


@router.get("/claims")
async def list_claims(
    request: Request,
    workspace_id: Optional[str] = Query(None, description="Filter to specific workspace"),
    limit: Optional[int] = Query(None, description="Maximum items per page", ge=1, le=200),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    db_infra: DatabaseInfra = Depends(get_db_infra),
) -> ClaimsResponse:
    """
    List active bead claims for a project.

    Claims indicate which workspaces are actively working on which beads.
    When an agent runs `bdh update <bead_id> --status in_progress`, they
    claim that bead exclusively within the project.

    Args:
        workspace_id: Optional. Filter to claims by a specific workspace.
        limit: Maximum number of claims to return (default 50, max 200).
        cursor: Pagination cursor from previous response for fetching next page.

    Returns:
        List of active claims with bead_id, workspace info, and claim time.
        Ordered by most recently claimed first.
        Includes has_more and next_cursor for pagination.
    """
    project_id = await get_project_from_auth(request, db_infra)

    server_db = db_infra.get_manager("server")

    # Validate pagination params
    try:
        validated_limit, cursor_data = validate_pagination_params(limit, cursor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Validate workspace_id if provided
    validated_workspace_id = None
    if workspace_id:
        try:
            validated_workspace_id = validate_workspace_id(workspace_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    # Build query with cursor-based pagination
    conditions: list[str] = []
    params: list[object] = []
    param_idx = 1

    conditions.append(f"project_id = ${param_idx}")
    params.append(UUID(project_id))
    param_idx += 1

    if validated_workspace_id:
        conditions.append(f"workspace_id = ${param_idx}")
        params.append(validated_workspace_id)
        param_idx += 1

    # Apply cursor (claimed_at < cursor_timestamp for DESC order)
    if cursor_data and "claimed_at" in cursor_data:
        try:
            cursor_timestamp = datetime.fromisoformat(cursor_data["claimed_at"])
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid cursor timestamp: {e}")
        conditions.append(f"claimed_at < ${param_idx}")
        params.append(cursor_timestamp)
        param_idx += 1

    # Fetch limit + 1 to detect has_more
    params.append(validated_limit + 1)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT bead_id, workspace_id, alias, human_name, claimed_at, project_id
        FROM {{{{tables.bead_claims}}}}
        {where_clause}
        ORDER BY claimed_at DESC
        LIMIT ${param_idx}
    """

    rows = await server_db.fetch_all(query, *params)

    # Check if there are more results
    has_more = len(rows) > validated_limit
    rows = rows[:validated_limit]  # Trim to requested limit

    claims = [
        Claim(
            bead_id=row["bead_id"],
            workspace_id=str(row["workspace_id"]),
            alias=row["alias"],
            human_name=row["human_name"],
            claimed_at=row["claimed_at"].isoformat(),
            project_id=str(row["project_id"]),
        )
        for row in rows
    ]

    # Generate next_cursor if there are more results
    next_cursor = None
    if has_more and claims:
        last_claim = claims[-1]
        next_cursor = encode_cursor({"claimed_at": last_claim.claimed_at})

    return ClaimsResponse(claims=claims, has_more=has_more, next_cursor=next_cursor)
