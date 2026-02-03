"""Test library mode: create_app() with external DB and Redis connections."""

import asyncio
import os
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from aweb.auth import hash_api_key
from beadhub.api import create_app
from beadhub.db import DatabaseInfra


@pytest.fixture
def redis_url():
    """Return test Redis URL."""
    return os.getenv("BEADHUB_TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.mark.asyncio
async def test_create_app_library_mode(db_infra, redis_url):
    """Test that create_app accepts external db_infra and redis."""
    # Create external Redis (part of what we're testing - library mode accepts external redis)
    redis = await Redis.from_url(redis_url, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        # Library mode: create app with external connections
        app = create_app(db_infra=db_infra, redis=redis)

        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                # Health check should work
                resp = await client.get("/health")
                assert resp.status_code == 200

                # Create a real workspace + project context and authenticate.
                aweb_resp = await client.post(
                    "/v1/init",
                    json={
                        "project_slug": "library-mode-test",
                        "project_name": "library-mode-test",
                        "alias": "test-agent",
                        "human_name": "Test User",
                        "agent_type": "agent",
                    },
                )
                assert aweb_resp.status_code == 200, aweb_resp.text
                api_key = aweb_resp.json()["api_key"]
                headers = {"Authorization": f"Bearer {api_key}"}

                reg_resp = await client.post(
                    "/v1/workspaces/register",
                    json={"repo_origin": "git@github.com:test/library-mode-test.git", "role": "agent"},
                    headers=headers,
                )
                assert reg_resp.status_code == 200, reg_resp.text
                init_data = reg_resp.json()

                # Register an agent (uses Redis)
                payload = {
                    "workspace_id": init_data["workspace_id"],
                    "alias": "test-agent",
                }
                resp = await client.post("/v1/agents/register", json=payload, headers=headers)
                assert resp.status_code == 200
                data = resp.json()
                assert data["agent"]["alias"] == "test-agent"

                # Beads upload: verify route is accessible under project API key.
                resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "test-repo",
                        "issues": [{"id": "bd-1", "title": "Test", "status": "open"}],
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_library_mode_validation():
    """Test that library mode requires both db_infra and redis, or neither."""
    # Only db_infra provided - should fail
    with pytest.raises(ValueError, match="Library mode requires both"):
        create_app(db_infra=DatabaseInfra())

    # Only redis provided - should fail
    redis = await Redis.from_url("redis://localhost:6379/15", decode_responses=True)
    try:
        with pytest.raises(ValueError, match="Library mode requires both"):
            create_app(redis=redis)
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_library_mode_requires_initialized_db_infra(redis_url):
    """Test that library mode rejects uninitialized db_infra."""
    db_infra = DatabaseInfra()  # NOT initialized
    redis = await Redis.from_url(redis_url, decode_responses=True)

    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")

    try:
        with pytest.raises(ValueError, match="db_infra must be initialized.*initialize"):
            create_app(db_infra=db_infra, redis=redis)
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_standalone_mode_still_works(db_infra_uninitialized, redis_url, monkeypatch):
    """Test that standalone mode (no external connections) still works."""
    # db_infra_uninitialized fixture creates test database and sets DATABASE_URL
    # We ignore the uninitialized infra object - standalone mode creates its own
    monkeypatch.setenv("REDIS_URL", redis_url)

    # Standalone mode: create app without external connections
    app = create_app()

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Health check should work
            resp = await client.get("/health")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_library_mode_concurrent_requests(db_infra, redis_url):
    """Test that library mode handles concurrent requests correctly."""
    redis = await Redis.from_url(redis_url, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await redis.flushdb()

    try:
        app = create_app(db_infra=db_infra, redis=redis)

        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                aweb_resp = await client.post(
                    "/v1/init",
                    json={
                        "project_slug": "library-mode-concurrent",
                        "project_name": "library-mode-concurrent",
                        "alias": "coordinator",
                        "human_name": "Coordinator",
                        "agent_type": "agent",
                    },
                )
                assert aweb_resp.status_code == 200, aweb_resp.text
                api_key = aweb_resp.json()["api_key"]
                headers = {"Authorization": f"Bearer {api_key}"}

                reg_resp = await client.post(
                    "/v1/workspaces/register",
                    json={
                        "repo_origin": "git@github.com:test/library-mode-concurrent.git",
                        "role": "agent",
                    },
                    headers=headers,
                )
                assert reg_resp.status_code == 200, reg_resp.text
                init_data = reg_resp.json()

                # Pre-create agents + API keys (aweb) and matching workspaces (beadhub) so
                # each concurrent request can authenticate as its own agent identity.
                server_db = db_infra.get_manager("server")
                aweb_db = db_infra.get_manager("aweb")
                project_uuid = uuid.UUID(init_data["project_id"])
                repo_uuid = uuid.UUID(init_data["repo_id"])

                agent_api_keys: dict[int, str] = {}
                for i in range(10):
                    workspace_id = uuid.UUID(f"00000000-0000-0000-0000-{i:012d}")
                    api_key = f"aw_sk_{uuid.uuid4().hex}"
                    agent_api_keys[i] = api_key

                    await aweb_db.execute(
                        """
                        INSERT INTO {{tables.agents}} (agent_id, project_id, alias, human_name, agent_type)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        workspace_id,
                        project_uuid,
                        f"agent-{i}",
                        "Test User",
                        "agent",
                    )
                    await aweb_db.execute(
                        """
                        INSERT INTO {{tables.api_keys}} (project_id, agent_id, key_prefix, key_hash, is_active)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        project_uuid,
                        workspace_id,
                        api_key[:12],
                        hash_api_key(api_key),
                        True,
                    )
                    await server_db.execute(
                        """
                        INSERT INTO {{tables.workspaces}}
                            (workspace_id, project_id, repo_id, alias, human_name)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        workspace_id,
                        project_uuid,
                        repo_uuid,
                        f"agent-{i}",
                        "Test User",
                    )

                # Fire 10 concurrent requests
                async def register_agent(i: int):
                    # Each agent gets its own workspace
                    workspace_id = f"00000000-0000-0000-0000-{i:012d}"
                    payload = {
                        "workspace_id": workspace_id,
                        "alias": f"agent-{i}",
                    }
                    resp = await client.post(
                        "/v1/agents/register",
                        json=payload,
                        headers={"Authorization": f"Bearer {agent_api_keys[i]}"},
                    )
                    return resp.status_code

                results = await asyncio.gather(*[register_agent(i) for i in range(10)])

                # All requests should succeed
                assert all(status == 200 for status in results)

                # Verify health check still works
                resp = await client.get("/health")
                assert resp.status_code == 200
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_library_mode_can_disable_bootstrap_routes(db_infra, redis_url):
    """Test that proxy-style embeddings can disable bootstrap routes like /v1/init."""
    redis = await Redis.from_url(redis_url, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        pytest.skip("Redis is not available")

    try:
        app = create_app(db_infra=db_infra, redis=redis, enable_bootstrap_routes=False)
        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/v1/init" not in paths
    finally:
        await redis.aclose()
