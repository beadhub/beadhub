"""Reservations API - view active resource locks."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from aweb.aweb_introspection import get_project_from_auth

from ..db import DatabaseInfra, get_db_infra

router = APIRouter(prefix="/v1", tags=["reservations"])


class ReservationView(BaseModel):
    project_id: str
    resource_key: str
    holder_agent_id: str
    holder_alias: str
    acquired_at: str
    expires_at: str
    metadata: dict[str, object]


class ReservationListResponse(BaseModel):
    reservations: list[ReservationView]


@router.get("/reservations")
async def list_reservations(
    request: Request,
    prefix: Optional[str] = Query(None, description="Optional resource key prefix filter"),
    db_infra: DatabaseInfra = Depends(get_db_infra),
) -> ReservationListResponse:
    project_id = await get_project_from_auth(request, db_infra)
    server_db = db_infra.get_manager("server")

    conditions = ["project_id = $1", "expires_at > NOW()"]
    params: list[object] = [UUID(project_id)]

    if prefix:
        conditions.append(f"resource_key LIKE ${len(params) + 1}")
        params.append(f"{prefix}%")

    where_clause = " AND ".join(conditions)
    rows = await server_db.fetch_all(
        f"""
        SELECT project_id, resource_key, holder_agent_id, holder_alias,
               acquired_at, expires_at, metadata_json
        FROM {{{{tables.reservations}}}}
        WHERE {where_clause}
        ORDER BY resource_key ASC
        """,
        *params,
    )

    return ReservationListResponse(
        reservations=[
            ReservationView(
                project_id=str(row["project_id"]),
                resource_key=row["resource_key"],
                holder_agent_id=str(row["holder_agent_id"]),
                holder_alias=row["holder_alias"],
                acquired_at=row["acquired_at"].isoformat(),
                expires_at=row["expires_at"].isoformat(),
                metadata=dict(row["metadata_json"] or {}),
            )
            for row in rows
        ]
    )
