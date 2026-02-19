"""Integration tests for POST /v1/workspaces/heartbeat endpoint."""

import logging
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app

logger = logging.getLogger(__name__)

TEST_REDIS_URL = "redis://localhost:6379/15"
TEST_REPO_ORIGIN = "git@github.com:anthropic/beadhub.git"
CANONICAL_ORIGIN = "github.com/anthropic/beadhub"


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def heartbeat_payload(init: dict, **overrides) -> dict:
    """Build a heartbeat request payload from init_workspace output."""
    base = {
        "workspace_id": init["workspace_id"],
        "alias": init["alias"],
        "repo_origin": TEST_REPO_ORIGIN,
        "human_name": "Test Human",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_heartbeat_basic(db_infra, init_workspace):
    """Heartbeat succeeds for a registered workspace."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init),
                )
                assert resp.status_code == 200, resp.text
                data = resp.json()
                assert data["ok"] is True
                assert data["workspace_id"] == init["workspace_id"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_updates_presence(db_infra, init_workspace):
    """Heartbeat updates Redis presence."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init, current_branch="feature/test"),
                )
                assert resp.status_code == 200, resp.text

                # Check beadhub Redis presence
                presence_key = f"presence:{init['workspace_id']}"
                presence = await redis.hgetall(presence_key)
                assert presence, "Beadhub presence should be set after heartbeat"
                assert presence["alias"] == "alice-agent"
                assert presence["current_branch"] == "feature/test"

                # Check aweb agent-level Redis presence
                aweb_key = f"aweb:presence:{init['workspace_id']}"
                aweb_presence = await redis.hgetall(aweb_key)
                assert aweb_presence, "Aweb agent presence should be set after heartbeat"
                assert aweb_presence["agent_id"] == init["workspace_id"]
                assert aweb_presence["alias"] == "alice-agent"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_wrong_project(db_infra, init_workspace):
    """Heartbeat with mismatched workspace identity returns 403."""
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
                # Register workspace in project A
                init_a = await init_workspace(
                    client,
                    project_slug=f"hb-a-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                # Register workspace in project B
                init_b = await init_workspace(
                    client,
                    project_slug=f"hb-b-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="bob-agent",
                    human_name="Test Human",
                    role="agent",
                )

                # Use project B's API key but project A's workspace_id
                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init_b["api_key"]),
                    json=heartbeat_payload(init_a),
                )
                assert resp.status_code == 403, resp.text
                assert "workspace_id does not match API key identity" in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_alias_mismatch(db_infra, init_workspace):
    """Heartbeat with wrong alias returns 409."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init, alias="wrong-alias"),
                )
                assert resp.status_code == 409, resp.text
                assert "Alias mismatch" in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_deleted_workspace(db_infra, init_workspace):
    """Heartbeat with a soft-deleted workspace returns 410."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                # Soft-delete workspace
                delete_resp = await client.delete(
                    f"/v1/workspaces/{init['workspace_id']}",
                    headers=auth_headers(init["api_key"]),
                )
                assert delete_resp.status_code == 200, delete_resp.text

                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init),
                )
                assert resp.status_code == 410, resp.text
                assert "deleted" in resp.json()["detail"].lower()
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_updates_current_branch(db_infra, init_workspace):
    """Heartbeat with current_branch updates the workspaces table."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                # Send heartbeat with branch
                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init, current_branch="feature/xyz"),
                )
                assert resp.status_code == 200, resp.text

                # Verify via list workspaces
                list_resp = await client.get(
                    "/v1/workspaces",
                    headers=auth_headers(init["api_key"]),
                    params={"include_presence": "false"},
                )
                assert list_resp.status_code == 200, list_resp.text
                workspaces = list_resp.json()["workspaces"]
                ws = next(w for w in workspaces if w["workspace_id"] == init["workspace_id"])
                assert ws["branch"] == "feature/xyz"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_repo_mismatch(db_infra, init_workspace):
    """Heartbeat with a different repo_origin than registered returns 400."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                # Use a different repo_origin
                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init, repo_origin="git@github.com:other/repo.git"),
                )
                assert resp.status_code == 400, resp.text
                assert "Repo mismatch" in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_stores_timezone(db_infra, init_workspace):
    """Heartbeat with timezone stores it in DB and Redis presence."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init, timezone="Europe/Madrid"),
                )
                assert resp.status_code == 200, resp.text

                # Verify DB column
                server_db = db_infra.get_manager("server")
                row = await server_db.fetch_one(
                    "SELECT timezone FROM {{tables.workspaces}} WHERE workspace_id = $1",
                    uuid.UUID(init["workspace_id"]),
                )
                assert row is not None
                assert row["timezone"] == "Europe/Madrid"

                # Verify Redis presence hash
                presence_key = f"presence:{init['workspace_id']}"
                presence = await redis.hgetall(presence_key)
                assert presence.get("timezone") == "Europe/Madrid"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_deleted_repo(db_infra, init_workspace):
    """Heartbeat when the repo was deleted returns 410."""
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
                init = await init_workspace(
                    client,
                    project_slug=f"hb-{uuid.uuid4().hex[:8]}",
                    repo_origin=TEST_REPO_ORIGIN,
                    alias="alice-agent",
                    human_name="Test Human",
                    role="agent",
                )

                # Soft-delete the repo directly in the DB
                server_db = db_infra.get_manager("server")
                await server_db.execute(
                    "UPDATE {{tables.repos}} SET deleted_at = NOW() WHERE id = $1",
                    init["repo_id"],
                )

                resp = await client.post(
                    "/v1/workspaces/heartbeat",
                    headers=auth_headers(init["api_key"]),
                    json=heartbeat_payload(init),
                )
                assert resp.status_code == 410, resp.text
                assert "deleted" in resp.json()["detail"].lower()
    finally:
        await redis.flushdb()
        await redis.aclose()
