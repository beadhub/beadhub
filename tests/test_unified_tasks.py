"""Tests for unified /v1/tasks endpoints with beads fallback.

The /v1/tasks endpoints serve native aweb tasks and, for projects that use
beads, also return beads issues mapped to the aweb task shape. Native tasks
take priority; beads issues fill in for projects that haven't migrated yet.
"""

import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app

TEST_REDIS_URL = "redis://localhost:6379/15"


async def _setup_project(client):
    """Create a project with one agent and return setup dict."""
    project_slug = f"utask-{uuid.uuid4().hex[:8]}"
    repo_origin = f"git@github.com:test/unified-{project_slug}.git"

    resp = await client.post(
        "/v1/init",
        json={
            "project_slug": project_slug,
            "project_name": project_slug,
            "alias": f"agent-{uuid.uuid4().hex[:4]}",
            "human_name": "Test Agent",
            "agent_type": "agent",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    api_key = data["api_key"]
    agent_id = data["agent_id"]

    reg = await client.post(
        "/v1/workspaces/register",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"repo_origin": repo_origin, "role": "developer"},
    )
    assert reg.status_code == 200, reg.text

    return {
        "project_slug": project_slug,
        "workspace_id": reg.json()["workspace_id"],
        "api_key": api_key,
        "agent_id": agent_id,
        "repo_origin": repo_origin,
    }


async def _upload_beads_issues(client, api_key, issues, repo="github.com/test/repo", branch="main"):
    """Upload beads issues via the beads upload endpoint."""
    resp = await client.post(
        "/v1/beads/upload",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"repo": repo, "branch": branch, "issues": issues},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_tasks_list_includes_beads_issues(db_infra):
    """GET /v1/tasks returns beads issues mapped to task shape."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                setup = await _setup_project(client)
                headers = {"Authorization": f"Bearer {setup['api_key']}"}

                # Upload a beads issue
                await _upload_beads_issues(
                    client,
                    setup["api_key"],
                    [
                        {
                            "id": "bd-1",
                            "title": "Beads bug report",
                            "status": "open",
                            "priority": 1,
                            "issue_type": "bug",
                            "created_by": "alice",
                        },
                    ],
                )

                # GET /v1/tasks should include the beads issue
                resp = await client.get("/v1/tasks", headers=headers)
                assert resp.status_code == 200, resp.text
                tasks = resp.json()["tasks"]
                matching = [t for t in tasks if t["task_ref"] == "bd-1"]
                assert len(matching) == 1, f"Expected beads issue in task list, got {tasks}"
                task = matching[0]
                assert task["title"] == "Beads bug report"
                assert task["task_type"] == "bug"
                assert task["priority"] == 1
                assert task["status"] == "open"
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_tasks_detail_falls_back_to_beads(db_infra):
    """GET /v1/tasks/{ref} returns beads issue when no native task matches."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                setup = await _setup_project(client)
                headers = {"Authorization": f"Bearer {setup['api_key']}"}

                await _upload_beads_issues(
                    client,
                    setup["api_key"],
                    [
                        {
                            "id": "bd-42",
                            "title": "Legacy beads issue",
                            "status": "in_progress",
                            "priority": 2,
                            "issue_type": "feature",
                            "created_by": "bob",
                            "description": "A detailed description",
                            "labels": ["backend", "api"],
                        },
                    ],
                )

                # GET /v1/tasks/bd-42 should resolve from beads
                resp = await client.get("/v1/tasks/bd-42", headers=headers)
                assert resp.status_code == 200, resp.text
                task = resp.json()
                assert task["task_ref"] == "bd-42"
                assert task["title"] == "Legacy beads issue"
                assert task["task_type"] == "feature"
                assert task["priority"] == 2
                assert task["status"] == "in_progress"
                assert task["description"] == "A detailed description"
                assert task["labels"] == ["backend", "api"]
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_tasks_detail_prefers_native_over_beads(db_infra):
    """Native aweb tasks take priority when ref matches both sources."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                setup = await _setup_project(client)
                headers = {"Authorization": f"Bearer {setup['api_key']}"}

                # Create a native task
                task_resp = await client.post(
                    "/v1/tasks",
                    headers=headers,
                    json={"title": "Native task", "task_type": "bug", "priority": 1},
                )
                assert task_resp.status_code == 200, task_resp.text
                task_ref = task_resp.json()["task_ref"]

                # Upload a beads issue with the same ID (unlikely but tests priority)
                await _upload_beads_issues(
                    client,
                    setup["api_key"],
                    [
                        {
                            "id": task_ref,
                            "title": "Beads version of same issue",
                            "status": "open",
                            "priority": 3,
                            "issue_type": "task",
                            "created_by": "charlie",
                        },
                    ],
                )

                # Native should win
                resp = await client.get(f"/v1/tasks/{task_ref}", headers=headers)
                assert resp.status_code == 200, resp.text
                task = resp.json()
                assert task["title"] == "Native task", "Native task should take priority over beads"
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_tasks_list_merges_native_and_beads(db_infra):
    """GET /v1/tasks returns both native tasks and beads issues."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                setup = await _setup_project(client)
                headers = {"Authorization": f"Bearer {setup['api_key']}"}

                # Create a native task
                task_resp = await client.post(
                    "/v1/tasks",
                    headers=headers,
                    json={"title": "Native task", "task_type": "task", "priority": 1},
                )
                assert task_resp.status_code == 200, task_resp.text
                native_ref = task_resp.json()["task_ref"]

                # Upload a beads issue
                await _upload_beads_issues(
                    client,
                    setup["api_key"],
                    [
                        {
                            "id": "bd-99",
                            "title": "Beads issue",
                            "status": "open",
                            "priority": 2,
                            "issue_type": "bug",
                            "created_by": "alice",
                        },
                    ],
                )

                # Both should appear
                resp = await client.get("/v1/tasks", headers=headers)
                assert resp.status_code == 200, resp.text
                tasks = resp.json()["tasks"]
                refs = {t["task_ref"] for t in tasks}
                assert native_ref in refs, f"Expected native task {native_ref} in {refs}"
                assert "bd-99" in refs, f"Expected beads issue bd-99 in {refs}"
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_tasks_list_filters_beads_by_labels(db_infra):
    """GET /v1/tasks?labels=X filters beads issues by label, not just native tasks."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                setup = await _setup_project(client)
                headers = {"Authorization": f"Bearer {setup['api_key']}"}

                # Upload two beads issues with different labels
                await _upload_beads_issues(
                    client,
                    setup["api_key"],
                    [
                        {
                            "id": "bd-labeled",
                            "title": "Has backend label",
                            "status": "open",
                            "priority": 1,
                            "labels": ["backend", "api"],
                        },
                        {
                            "id": "bd-unlabeled",
                            "title": "No matching label",
                            "status": "open",
                            "priority": 1,
                            "labels": ["frontend"],
                        },
                    ],
                )

                # Filter by labels=backend — should only return bd-labeled
                resp = await client.get("/v1/tasks", params={"labels": "backend"}, headers=headers)
                assert resp.status_code == 200, resp.text
                tasks = resp.json()["tasks"]
                refs = {t["task_ref"] for t in tasks}
                assert "bd-labeled" in refs, f"Expected bd-labeled in filtered results, got {refs}"
                assert (
                    "bd-unlabeled" not in refs
                ), f"bd-unlabeled should be excluded by label filter, got {refs}"
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_tasks_list_excludes_beads_when_assignee_filtered(db_infra):
    """GET /v1/tasks?assignee_agent_id=X excludes beads issues (they have no assignee)."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                setup = await _setup_project(client)
                headers = {"Authorization": f"Bearer {setup['api_key']}"}

                # Upload a beads issue
                await _upload_beads_issues(
                    client,
                    setup["api_key"],
                    [
                        {
                            "id": "bd-noassign",
                            "title": "Beads issue without assignee",
                            "status": "open",
                            "priority": 1,
                        },
                    ],
                )

                # Filter by assignee — beads issues should be excluded
                resp = await client.get(
                    "/v1/tasks",
                    params={"assignee_agent_id": setup["agent_id"]},
                    headers=headers,
                )
                assert resp.status_code == 200, resp.text
                tasks = resp.json()["tasks"]
                refs = {t["task_ref"] for t in tasks}
                assert (
                    "bd-noassign" not in refs
                ), f"Beads issues should be excluded when filtering by assignee, got {refs}"
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_ready_excludes_assigned_tasks(db_infra):
    """GET /v1/tasks/ready excludes tasks that have an assignee."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                setup = await _setup_project(client)
                headers = {"Authorization": f"Bearer {setup['api_key']}"}

                agent_id = setup["agent_id"]

                # Create two open tasks
                resp = await client.post(
                    "/v1/tasks",
                    headers=headers,
                    json={"title": "Unclaimed task", "task_type": "task", "priority": 2},
                )
                assert resp.status_code == 200, resp.text

                resp = await client.post(
                    "/v1/tasks",
                    headers=headers,
                    json={"title": "Claimed task", "task_type": "task", "priority": 2},
                )
                assert resp.status_code == 200, resp.text
                claimed_ref = resp.json()["task_ref"]

                # Assign the second task without changing status (stays open)
                resp = await client.patch(
                    f"/v1/tasks/{claimed_ref}",
                    headers=headers,
                    json={"assignee_agent_id": agent_id},
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["status"] == "open"
                assert resp.json()["assignee_agent_id"] is not None

                # GET /v1/tasks/ready should only return the unclaimed task
                resp = await client.get("/v1/tasks/ready", headers=headers)
                assert resp.status_code == 200, resp.text
                tasks = resp.json()["tasks"]
                titles = [t["title"] for t in tasks]
                refs = [t["task_ref"] for t in tasks]
                assert "Unclaimed task" in titles
                assert "Claimed task" not in titles
                assert claimed_ref not in refs
    finally:
        await redis.aclose()
