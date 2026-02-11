"""Tests for /v1/claims endpoint."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app

TEST_REDIS_URL = "redis://localhost:6379/15"
TEST_REPO_ORIGIN = "git@github.com:anthropic/beadhub.git"


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def init_project(
    client: AsyncClient,
    *,
    project_slug: str,
    repo_origin: str = TEST_REPO_ORIGIN,
    alias: str | None = None,
    human_name: str = "Test User",
) -> dict:
    if alias is None:
        alias = f"test-agent-{uuid.uuid4().hex[:8]}"
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
    assert api_key.startswith("aw_sk_")

    reg = await client.post(
        "/v1/workspaces/register",
        headers=auth_headers(api_key),
        json={"repo_origin": repo_origin, "role": "agent"},
    )
    assert reg.status_code == 200, reg.text
    data = reg.json()
    data["api_key"] = api_key
    return data


@pytest.mark.asyncio
async def test_claims_requires_auth(db_infra):
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
                resp = await client.get("/v1/claims")
                assert resp.status_code == 401

                init = await init_project(client, project_slug=f"claims-{uuid.uuid4().hex[:8]}")
                resp = await client.get("/v1/claims", headers=auth_headers(init["api_key"]))
                assert resp.status_code == 200
                data = resp.json()
                assert "claims" in data
                assert "has_more" in data
                assert "next_cursor" in data
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_returns_empty_list_initially(db_infra):
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
                init = await init_project(client, project_slug=f"claims-{uuid.uuid4().hex[:8]}")
                resp = await client.get("/v1/claims", headers=auth_headers(init["api_key"]))
                assert resp.status_code == 200
                assert resp.json()["claims"] == []
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_validates_workspace_id(db_infra):
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
                init = await init_project(client, project_slug=f"claims-{uuid.uuid4().hex[:8]}")
                resp = await client.get(
                    "/v1/claims",
                    params={"workspace_id": "not-a-uuid"},
                    headers=auth_headers(init["api_key"]),
                )
                assert resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_returns_active_claims(db_infra):
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
                init = await init_project(
                    client, project_slug=f"claims-{uuid.uuid4().hex[:8]}", alias="claude-main"
                )
                project_id = uuid.UUID(init["project_id"])
                workspace_id = init["workspace_id"]

                server_db = db_infra.get_manager("server")
                await server_db.execute(
                    """
                    INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    project_id,
                    uuid.UUID(workspace_id),
                    "claude-main",
                    "Juan",
                    "bd-42",
                )

                resp = await client.get("/v1/claims", headers=auth_headers(init["api_key"]))
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["claims"]) == 1
                claim = data["claims"][0]
                assert claim["bead_id"] == "bd-42"
                assert claim["workspace_id"] == workspace_id
                assert claim["alias"] == "claude-main"
                assert "claimed_at" in claim
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_tenant_isolation(db_infra):
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
                init_a = await init_project(
                    client,
                    project_slug=f"project-a-{uuid.uuid4().hex[:8]}",
                    repo_origin="git@github.com:test/project-a.git",
                    alias="alice-agent",
                    human_name="Alice",
                )
                init_b = await init_project(
                    client,
                    project_slug=f"project-b-{uuid.uuid4().hex[:8]}",
                    repo_origin="git@github.com:test/project-b.git",
                    alias="bob-agent",
                    human_name="Bob",
                )

                server_db = db_infra.get_manager("server")
                await server_db.execute(
                    """
                    INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid.UUID(init_a["project_id"]),
                    uuid.UUID(init_a["workspace_id"]),
                    "alice-agent",
                    "Alice",
                    "bd-alice-1",
                )
                await server_db.execute(
                    """
                    INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid.UUID(init_b["project_id"]),
                    uuid.UUID(init_b["workspace_id"]),
                    "bob-agent",
                    "Bob",
                    "bd-bob-1",
                )

                resp = await client.get("/v1/claims", headers=auth_headers(init_a["api_key"]))
                assert resp.status_code == 200
                claims_a = resp.json()["claims"]
                assert len(claims_a) == 1
                assert claims_a[0]["bead_id"] == "bd-alice-1"

                resp = await client.get("/v1/claims", headers=auth_headers(init_b["api_key"]))
                assert resp.status_code == 200
                claims_b = resp.json()["claims"]
                assert len(claims_b) == 1
                assert claims_b[0]["bead_id"] == "bd-bob-1"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_filters_by_workspace_id(db_infra):
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
                project_slug = f"claims-{uuid.uuid4().hex[:8]}"
                init_1 = await init_project(
                    client, project_slug=project_slug, alias="claude-main", human_name="Juan"
                )
                init_2 = await init_project(
                    client, project_slug=project_slug, alias="claude-fe", human_name="Juan"
                )

                server_db = db_infra.get_manager("server")
                await server_db.execute(
                    """
                    INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid.UUID(init_1["project_id"]),
                    uuid.UUID(init_1["workspace_id"]),
                    "claude-main",
                    "Juan",
                    "bd-42",
                )
                await server_db.execute(
                    """
                    INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid.UUID(init_1["project_id"]),
                    uuid.UUID(init_2["workspace_id"]),
                    "claude-fe",
                    "Juan",
                    "bd-99",
                )

                headers = auth_headers(init_1["api_key"])
                resp = await client.get("/v1/claims", headers=headers)
                assert resp.status_code == 200
                assert len(resp.json()["claims"]) == 2

                resp = await client.get(
                    "/v1/claims",
                    params={"workspace_id": init_1["workspace_id"]},
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["claims"]) == 1
                assert data["claims"][0]["bead_id"] == "bd-42"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_pagination(db_infra):
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
                init = await init_project(
                    client, project_slug=f"claims-{uuid.uuid4().hex[:8]}", alias="claude-main"
                )

                server_db = db_infra.get_manager("server")
                base_time = datetime.now(timezone.utc)
                for i in range(5):
                    claim_time = base_time - timedelta(minutes=5 - i)
                    await server_db.execute(
                        """
                        INSERT INTO {{tables.bead_claims}}
                            (project_id, workspace_id, alias, human_name, bead_id, claimed_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        uuid.UUID(init["project_id"]),
                        uuid.UUID(init["workspace_id"]),
                        "claude-main",
                        "Juan",
                        f"bd-{i + 1}",
                        claim_time,
                    )

                headers = auth_headers(init["api_key"])
                resp = await client.get("/v1/claims", params={"limit": 2}, headers=headers)
                assert resp.status_code == 200
                data = resp.json()
                assert [c["bead_id"] for c in data["claims"]] == ["bd-5", "bd-4"]
                assert data["has_more"] is True
                assert data["next_cursor"]

                resp = await client.get(
                    "/v1/claims",
                    params={"limit": 2, "cursor": data["next_cursor"]},
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert [c["bead_id"] for c in data["claims"]] == ["bd-3", "bd-2"]
                assert data["has_more"] is True

                resp = await client.get(
                    "/v1/claims",
                    params={"limit": 2, "cursor": data["next_cursor"]},
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert [c["bead_id"] for c in data["claims"]] == ["bd-1"]
                assert data["has_more"] is False
                assert data["next_cursor"] is None
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_pagination_response_schema(db_infra):
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
                init = await init_project(client, project_slug=f"claims-{uuid.uuid4().hex[:8]}")
                resp = await client.get("/v1/claims", headers=auth_headers(init["api_key"]))
                assert resp.status_code == 200
                data = resp.json()
                assert "claims" in data
                assert "has_more" in data
                assert "next_cursor" in data
                assert data["has_more"] is False
                assert data["next_cursor"] is None
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_claims_invalid_cursor(db_infra):
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
                init = await init_project(client, project_slug=f"claims-{uuid.uuid4().hex[:8]}")
                resp = await client.get(
                    "/v1/claims",
                    params={"cursor": "invalid-cursor!!!"},
                    headers=auth_headers(init["api_key"]),
                )
                assert resp.status_code == 422
                assert "cursor" in resp.json()["detail"].lower()
    finally:
        await redis.flushdb()
        await redis.aclose()
