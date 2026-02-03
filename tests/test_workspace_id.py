"""Tests for workspace_id validation and routing."""

import json
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app
from beadhub.auth import validate_workspace_id
from beadhub.presence import _presence_key

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


class TestWorkspaceIdValidation:
    """Test workspace_id validation."""

    def test_valid_uuid(self):
        """Valid UUID should pass validation."""
        valid_id = str(uuid.uuid4())
        assert validate_workspace_id(valid_id) == valid_id

    def test_valid_uuid_uppercase(self):
        """Uppercase UUID should be normalized to lowercase."""
        valid_id = str(uuid.uuid4()).upper()
        result = validate_workspace_id(valid_id)
        assert result == valid_id.lower()

    def test_invalid_format(self):
        """Invalid format should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid workspace_id format"):
            validate_workspace_id("not-a-uuid")

    def test_empty_string(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="workspace_id cannot be empty"):
            validate_workspace_id("")

    def test_none_like(self):
        """None-like values should raise ValueError."""
        with pytest.raises(ValueError, match="workspace_id cannot be empty"):
            validate_workspace_id("   ")

    def test_path_rejected(self):
        """File paths (old project_key format) should be rejected."""
        with pytest.raises(ValueError, match="Invalid workspace_id format"):
            validate_workspace_id("/path/to/project")

    def test_partial_uuid(self):
        """Partial UUID should be rejected."""
        with pytest.raises(ValueError, match="Invalid workspace_id format"):
            validate_workspace_id("a1b2c3d4-5678-90ab-cdef")

    def test_uuid_with_braces_accepted(self):
        """UUID with braces is normalized (Python accepts this format)."""
        valid_id = str(uuid.uuid4())
        result = validate_workspace_id(f"{{{valid_id}}}")
        assert result == valid_id


class TestPresenceKeyStructure:
    """Test that presence keys use workspace_id only, not alias."""

    def test_presence_key_uses_workspace_id_only(self):
        """Presence key should be presence:{workspace_id} without alias."""
        workspace_id = str(uuid.uuid4())
        # The key should NOT include alias
        key = _presence_key(workspace_id)
        assert key == f"presence:{workspace_id}"
        # Verify it doesn't have extra segments
        assert key.count(":") == 1

    @pytest.mark.asyncio
    async def test_second_agent_registration_overwrites_first(self, db_infra):
        """Registering a new agent in same workspace overwrites the previous one."""
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
                    init = await _init_project_auth(
                        client,
                        project_slug="presence-overwrite",
                        repo_origin="git@github.com:test/presence-overwrite.git",
                        alias="agent-one",
                    )
                    client.headers.update(_auth_headers(init["api_key"]))

                    # Register first agent
                    payload1 = {
                        "workspace_id": init["workspace_id"],
                        "alias": "agent-one",
                        "program": "claude-code",
                    }
                    resp1 = await client.post("/v1/agents/register", json=payload1)
                    assert resp1.status_code == 200

                    # Register second agent in same workspace
                    payload2 = {
                        "workspace_id": init["workspace_id"],
                        "alias": "agent-one",
                        "program": "codex-cli",
                    }
                    resp2 = await client.post("/v1/agents/register", json=payload2)
                    assert resp2.status_code == 200

                    # List agents - should only show the second agent (overwrote first)
                    list_req = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "list_agents",
                            "arguments": {"workspace_id": init["workspace_id"]},
                        },
                    }
                    list_resp = await client.post("/mcp", json=list_req)
                    assert list_resp.status_code == 200

                    data = json.loads(list_resp.json()["result"]["content"][0]["text"])

                    # Only one agent should be present (the second one)
                    assert len(data["agents"]) == 1
                    assert data["agents"][0]["alias"] == "agent-one"
                    assert data["agents"][0]["program"] == "codex-cli"
        finally:
            await redis.flushdb()
            await redis.aclose()


class TestWorkspaceDiscovery:
    """Test GET /v1/workspaces/online endpoint for workspace discovery."""

    @pytest.mark.asyncio
    async def test_list_workspaces_returns_registered_agents(self, db_infra):
        """List online workspaces returns all registered workspaces with presence."""
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
                    init_1 = await _init_project_auth(
                        client,
                        project_slug="online-workspaces",
                        repo_origin="git@github.com:test/online-workspaces.git",
                        alias="frontend-bot",
                        human_name="Test User",
                    )
                    init_2 = await _init_project_auth(
                        client,
                        project_slug="online-workspaces",
                        repo_origin="git@github.com:test/online-workspaces.git",
                        alias="backend-bot",
                        human_name="Test User",
                    )
                    client.headers.update(_auth_headers(init_1["api_key"]))

                    # Register two agents in different workspaces
                    await client.post(
                        "/v1/agents/register",
                        json={
                            "workspace_id": init_1["workspace_id"],
                            "alias": "frontend-bot",
                            "program": "claude-code",
                            "repo": "beadhub",
                            "branch": "main",
                        },
                    )
                    await client.post(
                        "/v1/agents/register",
                        json={
                            "workspace_id": init_2["workspace_id"],
                            "alias": "backend-bot",
                            "program": "codex-cli",
                            "repo": "example-repo",
                            "branch": "develop",
                        },
                        headers=_auth_headers(init_2["api_key"]),
                    )

                    # List online workspaces (presence-based)
                    resp = await client.get("/v1/workspaces/online")
                    assert resp.status_code == 200
                    data = resp.json()

                    assert "workspaces" in data
                    assert len(data["workspaces"]) == 2

                    ws_ids = {w["workspace_id"] for w in data["workspaces"]}
                    assert init_1["workspace_id"] in ws_ids
                    assert init_2["workspace_id"] in ws_ids

                    # Verify workspace fields
                    ws1 = next(
                        w for w in data["workspaces"] if w["workspace_id"] == init_1["workspace_id"]
                    )
                    assert ws1["alias"] == "frontend-bot"
                    assert ws1["program"] == "claude-code"
                    # repo/branch no longer stored in workspace presence
                    assert "last_seen" in ws1
        finally:
            await redis.flushdb()
            await redis.aclose()

    @pytest.mark.asyncio
    async def test_list_workspaces_empty(self, db_infra):
        """Empty list when no workspaces have active presence."""
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
                    init = await _init_project_auth(
                        client,
                        project_slug="online-workspaces-empty",
                        repo_origin="git@github.com:test/online-workspaces-empty.git",
                        alias="idle-agent",
                        human_name="Test User",
                    )
                    resp = await client.get(
                        "/v1/workspaces/online", headers=_auth_headers(init["api_key"])
                    )
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["workspaces"] == []
                    assert data["has_more"] is False
        finally:
            await redis.flushdb()
            await redis.aclose()
