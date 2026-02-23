"""Tests for guarding workspace operations against deregistered/retired agents."""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from beadhub.api import create_app


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_deregistered_agent_rejected_on_workspace_register(db_infra, redis_client_async):
    """A deregistered agent cannot register a workspace."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            init = await client.post(
                "/v1/init",
                json={
                    "project_slug": "guard-test",
                    "alias": "guard-agent",
                    "agent_type": "agent",
                    "lifetime": "ephemeral",
                    "repo_origin": "git@github.com:test/guard.git",
                },
            )
            assert init.status_code == 200, init.text
            api_key = init.json()["api_key"]

            # Deregister the agent
            dereg = await client.delete("/v1/agents/me", headers=_auth_headers(api_key))
            assert dereg.status_code == 200, dereg.text

            # Attempt to register a workspace — should be rejected
            reg = await client.post(
                "/v1/workspaces/register",
                json={"repo_origin": "git@github.com:test/guard.git"},
                headers=_auth_headers(api_key),
            )
            assert reg.status_code == 410, reg.text
            assert "deregistered" in reg.json().get("detail", "").lower()
