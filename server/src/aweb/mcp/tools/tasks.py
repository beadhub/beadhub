"""MCP tools for project task coordination."""

from __future__ import annotations

import json

from aweb.coordination.tasks_service import (
    create_task,
    get_task,
    list_ready_tasks,
    list_tasks,
    update_task,
)
from aweb.mcp.auth import get_auth
from aweb.service_errors import NotFoundError, ValidationError


async def task_create(
    db_infra,
    *,
    title: str,
    description: str = "",
    notes: str = "",
    priority: int = 2,
    task_type: str = "task",
    labels: list[str] | None = None,
    parent_task_id: str = "",
    assignee: str = "",
) -> str:
    """Create a task in the authenticated project."""
    auth = get_auth()
    try:
        result = await create_task(
            db_infra,
            project_id=auth.project_id,
            created_by_agent_id=auth.agent_id,
            title=title,
            description=description,
            notes=notes,
            priority=priority,
            task_type=task_type,
            labels=labels or [],
            parent_task_id=parent_task_id or None,
            assignee_agent_id=assignee or None,
        )
    except ValidationError as exc:
        return json.dumps({"error": exc.detail})
    return json.dumps(result)


async def task_list(
    db_infra,
    *,
    status: str = "",
    assignee: str = "",
    task_type: str = "",
    priority: int = -1,
    labels: list[str] | None = None,
) -> str:
    """List tasks in the authenticated project."""
    auth = get_auth()
    try:
        tasks = await list_tasks(
            db_infra,
            project_id=auth.project_id,
            status=status or None,
            assignee_agent_id=assignee or None,
            task_type=task_type or None,
            priority=priority if priority >= 0 else None,
            labels=labels or None,
        )
    except ValidationError as exc:
        return json.dumps({"error": exc.detail})
    return json.dumps({"tasks": tasks})


async def task_ready(db_infra, *, unclaimed_only: bool = True) -> str:
    """List ready tasks in the authenticated project."""
    auth = get_auth()
    tasks = await list_ready_tasks(
        db_infra,
        project_id=auth.project_id,
        unclaimed=bool(unclaimed_only),
    )
    return json.dumps({"tasks": tasks})


async def task_get(db_infra, *, ref: str) -> str:
    """Get a task by ref or UUID."""
    auth = get_auth()
    try:
        task = await get_task(db_infra, project_id=auth.project_id, ref=ref)
    except NotFoundError:
        return json.dumps({"error": "Task not found"})
    return json.dumps(task)


async def task_close(db_infra, *, ref: str) -> str:
    """Close a task by ref or UUID."""
    auth = get_auth()
    try:
        task = await update_task(
            db_infra,
            project_id=auth.project_id,
            ref=ref,
            actor_agent_id=auth.agent_id,
            status="closed",
        )
    except (NotFoundError, ValidationError) as exc:
        return json.dumps({"error": exc.detail})
    task.pop("old_status", None)
    task.pop("claim_preacquired", None)
    return json.dumps(task)
