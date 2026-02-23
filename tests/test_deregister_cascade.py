"""Tests for deregister→workspace cascade via mutation hook."""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from beadhub.api import create_app


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_deregister_cascades_to_workspace_soft_delete(db_infra, redis_client_async):
    """When an ephemeral agent deregisters, its workspace is soft-deleted."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create an ephemeral agent with a workspace (repo_origin triggers workspace creation)
            init = await client.post(
                "/v1/init",
                json={
                    "project_slug": "cascade-test",
                    "alias": "cascade-agent",
                    "agent_type": "agent",
                    "lifetime": "ephemeral",
                    "repo_origin": "git@github.com:test/cascade.git",
                },
            )
            assert init.status_code == 200, init.text
            data = init.json()
            api_key = data["api_key"]

            # Verify workspace exists and is active
            ws_list = await client.get(
                "/v1/workspaces",
                headers=_auth_headers(api_key),
            )
            assert ws_list.status_code == 200, ws_list.text
            aliases = [w["alias"] for w in ws_list.json().get("workspaces", [])]
            assert "cascade-agent" in aliases

            # Deregister the ephemeral agent
            dereg = await client.delete(
                "/v1/agents/me",
                headers=_auth_headers(api_key),
            )
            assert dereg.status_code == 200, dereg.text

            # Workspace should be soft-deleted (not in active list)
            ws_list2 = await client.get(
                "/v1/workspaces",
                headers=_auth_headers(api_key),
            )
            assert ws_list2.status_code == 200, ws_list2.text
            aliases2 = [w["alias"] for w in ws_list2.json().get("workspaces", [])]
            assert "cascade-agent" not in aliases2


@pytest.mark.asyncio
async def test_deregister_without_workspace_is_noop(db_infra, redis_client_async):
    """Agent deregister without a corresponding workspace does not error."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create agent WITHOUT repo_origin (no workspace created)
            init = await client.post(
                "/v1/init",
                json={
                    "project_slug": "cascade-noop",
                    "alias": "noop-agent",
                    "agent_type": "agent",
                    "lifetime": "ephemeral",
                },
            )
            assert init.status_code == 200, init.text
            api_key = init.json()["api_key"]

            # Deregister should succeed even without a workspace
            dereg = await client.delete(
                "/v1/agents/me",
                headers=_auth_headers(api_key),
            )
            assert dereg.status_code == 200, dereg.text
            assert dereg.json()["status"] == "deregistered"
