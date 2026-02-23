"""Tests for AwebIdentity resolution with identity fields."""

from uuid import UUID

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from beadhub.api import create_app


@pytest.mark.asyncio
async def test_resolve_identity_includes_identity_fields(db_infra, redis_client_async):
    """resolve_aweb_identity populates did, custody, lifetime, status."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Bootstrap an agent via init (creates aweb identity)
            resp = await client.post(
                "/v1/init",
                json={
                    "project_slug": "test-resolve-identity",
                    "repo_origin": "git@github.com:test/resolve-identity.git",
                    "alias": "resolve-agent",
                    "role": "agent",
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            api_key = data["api_key"]

            # Use the API key to call workspace register, which exercises resolve_aweb_identity.
            # If it succeeds, the identity was resolved correctly.
            reg_resp = await client.post(
                "/v1/workspaces/register",
                json={"repo_origin": "git@github.com:test/resolve-identity.git"},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            assert reg_resp.status_code == 200, reg_resp.text

            # Verify the agent record in DB has identity fields
            aweb_db = db_infra.get_manager("aweb")
            agent = await aweb_db.fetch_one(
                """
                SELECT did, custody, lifetime, status
                FROM {{tables.agents}}
                WHERE agent_id = $1 AND deleted_at IS NULL
                """,
                UUID(data["agent_id"]),
            )
            assert agent is not None
            assert agent["did"] is not None
            assert agent["did"].startswith("did:key:z")
            assert agent["custody"] == "custodial"
            assert agent["lifetime"] == "ephemeral"
            assert agent["status"] == "active"
