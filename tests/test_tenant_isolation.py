"""Tests for tenant isolation in beads operations.

CRITICAL: These tests verify that project A cannot see project B's issues,
preventing data leakage in multi-tenant deployments.
"""

import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app

TEST_REDIS_URL = "redis://localhost:6379/15"


async def _init_project_auth(
    client: AsyncClient,
    *,
    project_slug: str,
    repo_origin: str,
    alias: str,
    human_name: str = "Test User",
) -> dict[str, str]:
    aweb_resp = await client.post(
        "/v1/init",
        json={
            "project_slug": project_slug,
            "project_name": project_slug,
            "alias": alias,
            "human_name": human_name,
            "agent_type": "agent",
        },
    )
    assert aweb_resp.status_code == 200, aweb_resp.text
    api_key = aweb_resp.json()["api_key"]

    resp = await client.post(
        "/v1/workspaces/register",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"repo_origin": repo_origin, "role": "agent"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    data["api_key"] = api_key
    return data


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_upload_requires_project_id_header(db_infra):
    """Upload without Authorization should return 401."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "my-repo",
                        "issues": [{"id": "bd-1", "title": "Test", "status": "open"}],
                    },
                )
                assert resp.status_code == 401
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_issues_query_requires_project_id_header(db_infra):
    """GET /issues without Authorization should return 401."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/v1/beads/issues", params={"repo": "my-repo"})
                assert resp.status_code == 401
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_ready_query_requires_project_id_header(db_infra):
    """GET /ready without Authorization should return 401."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/v1/beads/ready",
                    params={"workspace_id": str(uuid.uuid4())},
                )
                assert resp.status_code == 401
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_tenant_isolation_upload_and_query(db_infra):
    """Project A's issues should not be visible to project B.

    This is the critical tenant isolation test.
    """
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                init_a = await _init_project_auth(
                    client,
                    project_slug="tenant-iso-a",
                    repo_origin="git@github.com:test/tenant-iso-a.git",
                    alias="agent-a",
                )
                init_b = await _init_project_auth(
                    client,
                    project_slug="tenant-iso-b",
                    repo_origin="git@github.com:test/tenant-iso-b.git",
                    alias="agent-b",
                )

                # Upload issues for project A
                resp_a = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "shared-repo-name",
                        "issues": [
                            {
                                "id": "bd-tenant-a-1",
                                "title": "Project A Issue",
                                "status": "open",
                            },
                        ],
                    },
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert resp_a.status_code == 200
                assert resp_a.json()["issues_synced"] == 1

                # Upload issues for project B with SAME repo name
                resp_b = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "shared-repo-name",
                        "issues": [
                            {
                                "id": "bd-tenant-b-1",
                                "title": "Project B Issue",
                                "status": "open",
                            },
                        ],
                    },
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert resp_b.status_code == 200
                assert resp_b.json()["issues_synced"] == 1

                # Query as project A - should only see A's issues
                query_a = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "shared-repo-name"},
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert query_a.status_code == 200
                issues_a = query_a.json()["issues"]
                assert len(issues_a) == 1
                assert issues_a[0]["bead_id"] == "bd-tenant-a-1"

                # Query as project B - should only see B's issues
                query_b = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "shared-repo-name"},
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert query_b.status_code == 200
                issues_b = query_b.json()["issues"]
                assert len(issues_b) == 1
                assert issues_b[0]["bead_id"] == "bd-tenant-b-1"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_same_bead_id_different_projects(db_infra):
    """Same bead_id in different projects should not collide.

    Before fix: ON CONFLICT (repo, branch, bead_id) would overwrite.
    After fix: ON CONFLICT (project_id, repo, branch, bead_id) keeps separate.
    """
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                init_a = await _init_project_auth(
                    client,
                    project_slug="bead-collision-a",
                    repo_origin="git@github.com:test/bead-collision-a.git",
                    alias="agent-a",
                )
                init_b = await _init_project_auth(
                    client,
                    project_slug="bead-collision-b",
                    repo_origin="git@github.com:test/bead-collision-b.git",
                    alias="agent-b",
                )

                # Upload bd-shared-1 for project A
                resp_a = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "same-repo",
                        "issues": [
                            {"id": "bd-shared-1", "title": "A's version", "status": "open"},
                        ],
                    },
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert resp_a.status_code == 200

                # Upload bd-shared-1 for project B (same bead_id)
                resp_b = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "same-repo",
                        "issues": [
                            {
                                "id": "bd-shared-1",
                                "title": "B's version",
                                "status": "closed",
                            },
                        ],
                    },
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert resp_b.status_code == 200

                # Verify A's issue is unchanged
                query_a = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "same-repo"},
                    headers=_auth_headers(init_a["api_key"]),
                )
                issues_a = query_a.json()["issues"]
                assert len(issues_a) == 1
                assert issues_a[0]["title"] == "A's version"
                assert issues_a[0]["status"] == "open"

                # Verify B's issue has its own values
                query_b = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "same-repo"},
                    headers=_auth_headers(init_b["api_key"]),
                )
                issues_b = query_b.json()["issues"]
                assert len(issues_b) == 1
                assert issues_b[0]["title"] == "B's version"
                assert issues_b[0]["status"] == "closed"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_ready_endpoint_tenant_isolation(db_infra):
    """GET /ready should only return issues for the requesting project."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                init_a = await _init_project_auth(
                    client,
                    project_slug="ready-iso-a",
                    repo_origin="git@github.com:test/ready-iso-a.git",
                    alias="agent-a",
                )
                init_b = await _init_project_auth(
                    client,
                    project_slug="ready-iso-b",
                    repo_origin="git@github.com:test/ready-iso-b.git",
                    alias="agent-b",
                )

                # Upload ready issue for project A
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "ready-repo",
                        "issues": [
                            {
                                "id": "bd-ready-a",
                                "title": "A's ready",
                                "status": "open",
                                "priority": 1,
                            },
                        ],
                    },
                    headers=_auth_headers(init_a["api_key"]),
                )

                # Upload ready issue for project B
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "ready-repo",
                        "issues": [
                            {
                                "id": "bd-ready-b",
                                "title": "B's ready",
                                "status": "open",
                                "priority": 1,
                            },
                        ],
                    },
                    headers=_auth_headers(init_b["api_key"]),
                )

                # Query ready as project A
                ready_a = await client.get(
                    "/v1/beads/ready",
                    params={"workspace_id": init_a["workspace_id"], "repo": "ready-repo"},
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert ready_a.status_code == 200
                issues_a = ready_a.json()["issues"]
                assert len(issues_a) == 1
                assert issues_a[0]["bead_id"] == "bd-ready-a"

                # Query ready as project B
                ready_b = await client.get(
                    "/v1/beads/ready",
                    params={"workspace_id": init_b["workspace_id"], "repo": "ready-repo"},
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert ready_b.status_code == 200
                issues_b = ready_b.json()["issues"]
                assert len(issues_b) == 1
                assert issues_b[0]["bead_id"] == "bd-ready-b"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_notification_tenant_isolation(db_infra):
    """Project B should NOT receive notifications for Project A's bead changes.

    CRITICAL SECURITY TEST:
    Verifies that subscribing to a bead_id doesn't leak notifications
    across tenant boundaries when different projects use the same bead_id.

    Attack scenario this prevents:
    1. Project A uploads issue bd-shared with status 'open'
    2. Project B subscribes to notifications for bd-shared (same bead_id)
    3. Project A updates bd-shared to status 'closed'
    4. Project B should NOT receive notification about Project A's issue
    """
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                init_a = await _init_project_auth(
                    client,
                    project_slug="tenant-iso-notif-a",
                    repo_origin="git@github.com:test/tenant-iso-notif-a.git",
                    alias="a-agent",
                    human_name="Tenant A",
                )
                init_b = await _init_project_auth(
                    client,
                    project_slug="tenant-iso-notif-b",
                    repo_origin="git@github.com:test/tenant-iso-notif-b.git",
                    alias="b-agent",
                    human_name="Tenant B",
                )

                # Step 1: Project A uploads bd-shared with status 'open'
                resp_a1 = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "notif-repo",
                        "issues": [
                            {"id": "bd-shared", "title": "A's secret issue", "status": "open"},
                        ],
                    },
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert resp_a1.status_code == 200

                # Step 2: Project B subscribes to bd-shared notifications
                # Note: Project B also needs the bead to exist in their project for valid subscription
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "notif-repo",
                        "issues": [
                            {"id": "bd-shared", "title": "B's own issue", "status": "open"},
                        ],
                    },
                    headers=_auth_headers(init_b["api_key"]),
                )

                sub_resp = await client.post(
                    "/v1/subscriptions",
                    json={
                        "workspace_id": init_b["workspace_id"],
                        "alias": "b-agent",
                        "bead_id": "bd-shared",
                        "repo": "notif-repo",
                        "event_types": ["status_change"],
                    },
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert sub_resp.status_code == 200

                # Step 3: Project A updates bd-shared to 'closed' (triggers notification)
                resp_a2 = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "notif-repo",
                        "issues": [
                            {"id": "bd-shared", "title": "A's secret issue", "status": "closed"},
                        ],
                    },
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert resp_a2.status_code == 200

                # Step 4: Project B should NOT have received notification for A's change
                # The notification would be in B's workspace inbox
                inbox_resp = await client.get(
                    "/v1/messages/inbox",
                    params={"agent_id": init_b["workspace_id"]},
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert inbox_resp.status_code == 200
                messages = inbox_resp.json().get("messages", [])

                # Filter for bead notification messages by subject prefix
                bead_notifications = [
                    m for m in messages if m.get("subject", "").startswith("Bead status changed:")
                ]

                # CRITICAL ASSERTION: No cross-tenant notification leak
                # Project B should NOT receive notifications about Project A's bd-shared
                assert len(bead_notifications) == 0, (
                    f"SECURITY VIOLATION: Project B received {len(bead_notifications)} "
                    f"notification(s) for Project A's bead change. "
                    f"Messages: {bead_notifications}"
                )
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_status_endpoint_tenant_isolation(db_infra):
    """GET /v1/status should only return presences for the authenticated project.

    Without this check, calling /v1/status without filters could return Redis
    presence data across projects, leaking workspace info across tenant boundaries.
    """
    from beadhub.presence import update_agent_presence

    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                init_a = await _init_project_auth(
                    client,
                    project_slug="status-iso-a",
                    repo_origin="git@github.com:test/status-a.git",
                    alias="agent-a",
                    human_name="Tenant A",
                )
                init_b = await _init_project_auth(
                    client,
                    project_slug="status-iso-b",
                    repo_origin="git@github.com:test/status-b.git",
                    alias="agent-b",
                    human_name="Tenant B",
                )

                # Register presence for both workspaces in Redis
                await update_agent_presence(
                    redis,
                    init_a["workspace_id"],
                    alias="agent-a",
                    program="test-cli",
                    model="test-model",
                    human_name="Tenant A",
                    project_id=init_a["project_id"],
                    project_slug="status-iso-a",
                    repo_id=init_a["repo_id"],
                )
                await update_agent_presence(
                    redis,
                    init_b["workspace_id"],
                    alias="agent-b",
                    program="test-cli",
                    model="test-model",
                    human_name="Tenant B",
                    project_id=init_b["project_id"],
                    project_slug="status-iso-b",
                    repo_id=init_b["repo_id"],
                )

                # Query /v1/status as project A
                # Should only see agent-a, not agent-b
                resp_a = await client.get(
                    "/v1/status",
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert resp_a.status_code == 200
                data_a = resp_a.json()
                aliases_a = {agent["alias"] for agent in data_a["agents"]}
                assert "agent-a" in aliases_a, "Project A should see its own agent"
                assert "agent-b" not in aliases_a, (
                    f"SECURITY VIOLATION: Project A sees Project B's agent. "
                    f"Agents returned: {aliases_a}"
                )

                # Query /v1/status as project B
                # Should only see agent-b, not agent-a
                resp_b = await client.get(
                    "/v1/status",
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert resp_b.status_code == 200
                data_b = resp_b.json()
                aliases_b = {agent["alias"] for agent in data_b["agents"]}
                assert "agent-b" in aliases_b, "Project B should see its own agent"
                assert "agent-a" not in aliases_b, (
                    f"SECURITY VIOLATION: Project B sees Project A's agent. "
                    f"Agents returned: {aliases_b}"
                )
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_status_workspace_id_tenant_isolation(db_infra):
    """GET /status with workspace_id should reject workspaces from other projects.

    CRITICAL SECURITY TEST: Without this fix, a tenant could query status for ANY
    workspace across all tenants by knowing/guessing workspace UUIDs.

    Attack scenario this prevents:
    1. Tenant B knows/guesses workspace UUID belonging to Tenant A
    2. Tenant B queries /v1/status?workspace_id=<A's workspace> with tenant B auth
    3. Should return 404, NOT leak Tenant A's workspace data
    """
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                init_a = await _init_project_auth(
                    client,
                    project_slug="ws-iso-a",
                    repo_origin="git@github.com:test/ws-iso-a.git",
                    alias="agent-a",
                    human_name="Tenant A",
                )
                init_b = await _init_project_auth(
                    client,
                    project_slug="ws-iso-b",
                    repo_origin="git@github.com:test/ws-iso-b.git",
                    alias="agent-b",
                    human_name="Tenant B",
                )

                # Tenant A can query their own workspace
                resp_a = await client.get(
                    "/v1/status",
                    params={"workspace_id": init_a["workspace_id"]},
                    headers=_auth_headers(init_a["api_key"]),
                )
                assert resp_a.status_code == 200, "Tenant A should access own workspace"

                # Tenant B tries to query Tenant A's workspace - should fail
                resp_b = await client.get(
                    "/v1/status",
                    params={"workspace_id": init_a["workspace_id"]},
                    headers=_auth_headers(init_b["api_key"]),
                )
                assert resp_b.status_code == 404, (
                    f"SECURITY VIOLATION: Tenant B accessed Tenant A's workspace. "
                    f"Expected 404, got {resp_b.status_code}. Response: {resp_b.json()}"
                )
    finally:
        await redis.flushdb()
        await redis.aclose()
