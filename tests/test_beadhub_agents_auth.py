from __future__ import annotations

import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app
from beadhub.internal_auth import _internal_auth_header_value

TEST_REDIS_URL = "redis://localhost:6379/15"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_beadhub_agents_list_scoped_by_api_key(db_infra):
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
                init_a = await client.post(
                    "/v1/init",
                    json={
                        "project_slug": "agents-a",
                        "project_name": "agents-a",
                        "alias": "agent-a",
                        "human_name": "Agent A",
                        "agent_type": "agent",
                    },
                )
                assert init_a.status_code == 200, init_a.text
                api_key_a = init_a.json()["api_key"]

                init_b = await client.post(
                    "/v1/init",
                    json={
                        "project_slug": "agents-b",
                        "project_name": "agents-b",
                        "alias": "agent-b",
                        "human_name": "Agent B",
                        "agent_type": "agent",
                    },
                )
                assert init_b.status_code == 200, init_b.text
                api_key_b = init_b.json()["api_key"]

                list_a = await client.get("/v1/agents", headers=_auth_headers(api_key_a))
                assert list_a.status_code == 200, list_a.text
                aliases_a = [a.get("alias") for a in (list_a.json().get("agents") or [])]
                assert "agent-a" in aliases_a
                assert "agent-b" not in aliases_a

                # Verify identity fields are present
                agent_a = next(a for a in list_a.json()["agents"] if a["alias"] == "agent-a")
                assert agent_a["did"] is not None
                assert agent_a["did"].startswith("did:key:z")
                assert agent_a["custody"] == "custodial"
                assert agent_a["lifetime"] == "ephemeral"
                assert agent_a["lifecycle_status"] == "active"
                assert agent_a["access_mode"] == "open"

                list_b = await client.get("/v1/agents", headers=_auth_headers(api_key_b))
                assert list_b.status_code == 200, list_b.text
                aliases_b = [a.get("alias") for a in (list_b.json().get("agents") or [])]
                assert "agent-b" in aliases_b
                assert "agent-a" not in aliases_b
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beadhub_agents_list_accepts_valid_proxy_headers(monkeypatch, db_infra):
    secret = "test-secret"
    monkeypatch.setenv("BEADHUB_INTERNAL_AUTH_SECRET", secret)

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
                init = await client.post(
                    "/v1/init",
                    json={
                        "project_slug": "agents-proxy",
                        "project_name": "agents-proxy",
                        "alias": "agent-proxy",
                        "human_name": "Agent Proxy",
                        "agent_type": "agent",
                    },
                )
                assert init.status_code == 200, init.text
                project_id = init.json()["project_id"]
                actor_id = init.json()["agent_id"]

                principal_id = str(uuid.uuid4())
                internal_auth = _internal_auth_header_value(
                    secret=secret,
                    project_id=str(uuid.UUID(project_id)),
                    principal_type="u",
                    principal_id=principal_id,
                    actor_id=str(uuid.UUID(actor_id)),
                )

                resp = await client.get(
                    "/v1/agents",
                    headers={
                        "X-BH-Auth": internal_auth,
                        "X-Project-ID": project_id,
                        "X-User-ID": principal_id,
                        "X-Aweb-Actor-ID": actor_id,
                    },
                )
                assert resp.status_code == 200, resp.text
                aliases = [a.get("alias") for a in (resp.json().get("agents") or [])]
                assert "agent-proxy" in aliases
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beadhub_agents_list_rejects_invalid_proxy_signature(monkeypatch, db_infra):
    secret = "test-secret"
    monkeypatch.setenv("BEADHUB_INTERNAL_AUTH_SECRET", secret)

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
                init = await client.post(
                    "/v1/init",
                    json={
                        "project_slug": "agents-proxy-bad",
                        "project_name": "agents-proxy-bad",
                        "alias": "agent-proxy-bad",
                        "human_name": "Agent Proxy Bad",
                        "agent_type": "agent",
                    },
                )
                assert init.status_code == 200, init.text
                project_id = init.json()["project_id"]
                principal_id = str(uuid.uuid4())
                actor_id = str(uuid.uuid4())

                resp = await client.get(
                    "/v1/agents",
                    headers={
                        "X-BH-Auth": f"v2:{project_id}:u:{principal_id}:{actor_id}:deadbeef",
                        "X-Project-ID": project_id,
                        "X-User-ID": principal_id,
                        "X-Aweb-Actor-ID": actor_id,
                    },
                )
                assert resp.status_code == 401, resp.text
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beadhub_agents_list_does_not_trust_proxy_headers_without_secret(
    monkeypatch, db_infra
):
    monkeypatch.delenv("BEADHUB_INTERNAL_AUTH_SECRET", raising=False)
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)

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
                    "/v1/agents",
                    headers={
                        "X-BH-Auth": f"v2:{uuid.uuid4()}:u:{uuid.uuid4()}:{uuid.uuid4()}:deadbeef",
                        "X-Project-ID": str(uuid.uuid4()),
                        "X-User-ID": str(uuid.uuid4()),
                        "X-Aweb-Actor-ID": str(uuid.uuid4()),
                    },
                )
                assert resp.status_code == 401, resp.text
    finally:
        await redis.flushdb()
        await redis.aclose()
