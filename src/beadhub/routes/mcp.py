from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis

from beadhub.auth import verify_workspace_access
from beadhub.aweb_introspection import get_project_from_auth

from ..db import DatabaseInfra, get_db_infra
from ..presence import (
    get_workspace_ids_by_project_id,
    list_agent_presences_by_workspace_ids,
    update_agent_presence,
)
from ..redis_client import get_redis
from .beads import beads_ready as http_beads_ready
from .beads import get_issue_by_bead_id as http_get_issue
from .escalations import (
    CreateEscalationRequest,
    CreateEscalationResponse,
    create_escalation,
)
from .escalations import get_escalation as http_get_escalation
from .status import status as http_status
from .subscriptions import SubscribeRequest
from .subscriptions import list_subscriptions as http_list_subscriptions
from .subscriptions import subscribe as http_subscribe
from .subscriptions import unsubscribe as http_unsubscribe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])


def _rpc_error(id_value: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": id_value, "error": error}


def _rpc_result(id_value: Any, payload: Any) -> dict[str, Any]:
    # MCP clients expect text content with a JSON string payload.
    return {
        "jsonrpc": "2.0",
        "id": id_value,
        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }


TOOL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "register_agent",
        "description": "Register agent presence for a workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
                "alias": {"type": "string", "description": "Agent alias"},
                "human_name": {"type": "string", "description": "Human operator name"},
                "program": {"type": "string", "description": "Agent program name"},
                "model": {"type": "string", "description": "Model identifier"},
                "role": {"type": "string", "description": "Agent role"},
            },
            "required": ["workspace_id", "alias"],
        },
    },
    {
        "name": "list_agents",
        "description": "List all agents with active presence in the project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
            },
            "required": ["workspace_id"],
        },
    },
    {
        "name": "status",
        "description": "Get workspace status including agents, claims, and conflicts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
            },
            "required": ["workspace_id"],
        },
    },
    {
        "name": "get_ready_issues",
        "description": "List beads issues that are ready to work on (open, no blockers).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
                "repo": {"type": "string", "description": "Filter by repo canonical origin"},
                "branch": {"type": "string", "description": "Filter by branch"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["workspace_id"],
        },
    },
    {
        "name": "get_issue",
        "description": "Get details of a specific beads issue by bead_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bead_id": {"type": "string", "description": "Bead issue ID"},
            },
            "required": ["bead_id"],
        },
    },
    {
        "name": "subscribe_to_bead",
        "description": "Subscribe to status change notifications for a bead.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
                "bead_id": {"type": "string", "description": "Bead issue ID"},
                "repo": {"type": "string", "description": "Repo canonical origin"},
                "event_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Event types to subscribe to",
                },
            },
            "required": ["workspace_id", "bead_id"],
        },
    },
    {
        "name": "list_subscriptions",
        "description": "List active bead subscriptions for a workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
            },
            "required": ["workspace_id"],
        },
    },
    {
        "name": "unsubscribe",
        "description": "Remove a bead subscription.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
                "subscription_id": {"type": "string", "description": "Subscription ID"},
            },
            "required": ["workspace_id", "subscription_id"],
        },
    },
    {
        "name": "escalate",
        "description": "Create a human-in-the-loop escalation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID"},
                "alias": {"type": "string", "description": "Agent alias"},
                "subject": {"type": "string", "description": "Escalation subject"},
                "situation": {"type": "string", "description": "Description of the situation"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Options for the human to choose from",
                },
                "expires_in_hours": {"type": "integer", "description": "Hours until expiry"},
                "member_email": {"type": "string", "description": "Email to notify"},
            },
            "required": ["workspace_id", "alias", "subject", "situation"],
        },
    },
    {
        "name": "get_escalation",
        "description": "Get details of an escalation by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "escalation_id": {"type": "string", "description": "Escalation ID"},
            },
            "required": ["escalation_id"],
        },
    },
]

RESOURCE_CATALOG: list[dict[str, Any]] = [
    {
        "uri": "beadhub://status",
        "name": "Workspace status",
        "description": "Agents, claims, conflicts, and escalations for the current project.",
        "mimeType": "application/json",
    },
]


@router.post("/mcp")
async def mcp_entry(
    request: Request,
    payload: dict[str, Any],
    redis: Redis = Depends(get_redis),
    db_infra: DatabaseInfra = Depends(get_db_infra),
) -> dict[str, Any]:
    """JSON-RPC 2.0 entrypoint for BeadHub MCP tools.

    Clean-slate split:
    - mail/chat/locks live in aweb and are not exposed here
    - this surface is bead/workspace specific (ready issues, subscriptions, status, escalations)
    """
    rpc_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return _rpc_error(rpc_id, -32600, "Invalid jsonrpc version")

    # Authenticate before dispatching any method.
    try:
        await get_project_from_auth(request, db_infra)
    except HTTPException as exc:
        return _rpc_error(rpc_id, exc.status_code, str(exc.detail))

    method = payload.get("method")

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": TOOL_CATALOG}}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"resources": RESOURCE_CATALOG}}

    if method == "resources/read":
        return await _handle_resources_read(rpc_id, request, redis, db_infra, payload)

    if method == "tools/call":
        return await _handle_tools_call(rpc_id, request, redis, db_infra, payload)

    return _rpc_error(rpc_id, -32601, f"Method not found: {method}")


async def _handle_resources_read(
    rpc_id: Any,
    request: Request,
    redis: Redis,
    db_infra: DatabaseInfra,
    payload: dict[str, Any],
) -> dict[str, Any]:
    params = payload.get("params") or {}
    uri = params.get("uri")
    if not isinstance(uri, str) or not uri:
        return _rpc_error(rpc_id, -32602, "uri parameter is required")

    try:
        if uri == "beadhub://status":
            data = await http_status(
                request, workspace_id=None, repo_id=None, redis=redis, db_infra=db_infra
            )
        else:
            return _rpc_error(rpc_id, -32602, f"Unknown resource URI: {uri}")
    except HTTPException as exc:
        return _rpc_error(rpc_id, exc.status_code, str(exc.detail))
    except Exception:
        logger.exception("MCP resources/read failed: %s", uri)
        return _rpc_error(rpc_id, -32000, "Internal error")

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(data),
                }
            ]
        },
    }


async def _handle_tools_call(
    rpc_id: Any,
    request: Request,
    redis: Redis,
    db_infra: DatabaseInfra,
    payload: dict[str, Any],
) -> dict[str, Any]:
    params = payload.get("params") or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str):
        return _rpc_error(rpc_id, -32602, "Tool name must be a string")
    if not isinstance(arguments, dict):
        return _rpc_error(rpc_id, -32602, "Tool arguments must be an object")

    try:
        if name == "register_agent":
            result = await _tool_register_agent(request, redis, db_infra, arguments)
        elif name == "list_agents":
            result = await _tool_list_agents(request, redis, db_infra, arguments)
        elif name == "status":
            result = await _tool_status(request, redis, db_infra, arguments)
        elif name == "get_ready_issues":
            result = await _tool_get_ready_issues(request, db_infra, arguments)
        elif name == "get_issue":
            result = await _tool_get_issue(request, db_infra, arguments)
        elif name == "subscribe_to_bead":
            result = await _tool_subscribe_to_bead(request, db_infra, arguments)
        elif name == "list_subscriptions":
            result = await _tool_list_subscriptions(request, db_infra, arguments)
        elif name == "unsubscribe":
            result = await _tool_unsubscribe(request, db_infra, arguments)
        elif name == "escalate":
            result = await _tool_escalate(request, redis, db_infra, arguments)
        elif name == "get_escalation":
            result = await _tool_get_escalation(request, db_infra, arguments)
        else:
            return _rpc_error(rpc_id, -32601, f"Unknown tool: {name}")
    except HTTPException as exc:
        return _rpc_error(rpc_id, exc.status_code, str(exc.detail))
    except Exception:
        logger.exception("MCP tool call failed: %s", name)
        return _rpc_error(rpc_id, -32000, "Internal error")

    return _rpc_result(rpc_id, result)


async def _tool_register_agent(
    request: Request,
    redis: Redis,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(args.get("workspace_id") or "").strip()
    alias = str(args.get("alias") or "").strip()
    human_name = str(args.get("human_name") or "").strip()
    program = str(args.get("program") or "").strip() or None
    model = str(args.get("model") or "").strip() or None
    role = str(args.get("role") or "").strip() or None

    if not workspace_id or not alias:
        raise HTTPException(status_code=422, detail="workspace_id and alias are required")

    project_id = await verify_workspace_access(request, workspace_id, db_infra)
    await update_agent_presence(
        redis,
        workspace_id=workspace_id,
        alias=alias,
        human_name=human_name,
        project_id=project_id,
        project_slug=None,
        repo_id=None,
        program=program,
        model=model,
        current_branch=None,
        role=role,
        ttl_seconds=1800,
    )
    return {"ok": True}


async def _tool_list_agents(
    request: Request,
    redis: Redis,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(args.get("workspace_id") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id is required")
    project_id = await verify_workspace_access(request, workspace_id, db_infra)
    workspace_ids = await get_workspace_ids_by_project_id(redis, project_id)
    agents = await list_agent_presences_by_workspace_ids(redis, workspace_ids)
    return {"agents": agents}


async def _tool_status(
    request: Request,
    redis: Redis,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(args.get("workspace_id") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id is required")
    await verify_workspace_access(request, workspace_id, db_infra)
    return await http_status(request, workspace_id=workspace_id, redis=redis, db_infra=db_infra)


async def _tool_get_ready_issues(
    request: Request,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(args.get("workspace_id") or "").strip()
    repo = str(args.get("repo") or "").strip() or None
    branch = str(args.get("branch") or "").strip() or None
    limit_raw = args.get("limit")
    limit = 10
    if limit_raw is not None:
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="limit must be an integer")
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id is required")
    await verify_workspace_access(request, workspace_id, db_infra)
    return await http_beads_ready(
        request,
        workspace_id=workspace_id,
        repo=repo,
        branch=branch,
        limit=limit,
        db_infra=db_infra,
    )


async def _tool_get_issue(
    request: Request,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    bead_id = str(args.get("bead_id") or "").strip()
    if not bead_id:
        raise HTTPException(status_code=422, detail="bead_id is required")
    # get_issue endpoint already enforces project scoping.
    return await http_get_issue(bead_id=bead_id, request=request, db_infra=db_infra)


async def _tool_subscribe_to_bead(
    request: Request,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(args.get("workspace_id") or "").strip()
    bead_id = str(args.get("bead_id") or "").strip()
    repo = args.get("repo")
    event_types = args.get("event_types")
    if not workspace_id or not bead_id:
        raise HTTPException(status_code=422, detail="workspace_id and bead_id are required")
    project_id = await verify_workspace_access(request, workspace_id, db_infra)
    alias = await _get_workspace_alias_or_403(db_infra, project_id, workspace_id)
    payload_kwargs: dict[str, Any] = {
        "workspace_id": workspace_id,
        "alias": alias,
        "bead_id": bead_id,
        "repo": repo,
    }
    if isinstance(event_types, list):
        payload_kwargs["event_types"] = event_types
    payload = SubscribeRequest.model_validate(payload_kwargs)
    response = await http_subscribe(payload=payload, request=request, db_infra=db_infra)
    return response.model_dump()


async def _tool_list_subscriptions(
    request: Request,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(args.get("workspace_id") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id is required")
    project_id = await verify_workspace_access(request, workspace_id, db_infra)
    alias = await _get_workspace_alias_or_403(db_infra, project_id, workspace_id)
    response = await http_list_subscriptions(
        request=request,
        workspace_id=workspace_id,
        alias=alias,
        db_infra=db_infra,
    )
    return response.model_dump()


async def _tool_unsubscribe(
    request: Request,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(args.get("workspace_id") or "").strip()
    subscription_id = str(args.get("subscription_id") or "").strip()
    if not workspace_id or not subscription_id:
        raise HTTPException(status_code=422, detail="workspace_id and subscription_id are required")
    project_id = await verify_workspace_access(request, workspace_id, db_infra)
    alias = await _get_workspace_alias_or_403(db_infra, project_id, workspace_id)
    response = await http_unsubscribe(
        request=request,
        subscription_id=subscription_id,
        workspace_id=workspace_id,
        alias=alias,
        db_infra=db_infra,
    )
    return response.model_dump()


async def _get_workspace_alias_or_403(
    db_infra: DatabaseInfra, project_id: str, workspace_id: str
) -> str:
    server_db = db_infra.get_manager("server")
    row = await server_db.fetch_one(
        """
        SELECT alias
        FROM {{tables.workspaces}}
        WHERE workspace_id = $1 AND project_id = $2 AND deleted_at IS NULL
        """,
        UUID(workspace_id),
        UUID(project_id),
    )
    if not row:
        raise HTTPException(
            status_code=403, detail="Workspace not found or does not belong to your project"
        )
    return row["alias"]


async def _tool_escalate(
    request: Request,
    redis: Redis,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    payload = CreateEscalationRequest.model_validate(args)
    response: CreateEscalationResponse = await create_escalation(
        request=request, payload=payload, redis=redis, db_infra=db_infra
    )
    return response.model_dump()


async def _tool_get_escalation(
    request: Request,
    db_infra: DatabaseInfra,
    args: dict[str, Any],
) -> dict[str, Any]:
    escalation_id = str(args.get("escalation_id") or "").strip()
    if not escalation_id:
        raise HTTPException(status_code=422, detail="escalation_id is required")
    return await http_get_escalation(
        escalation_id=escalation_id, request=request, db_infra=db_infra
    )
