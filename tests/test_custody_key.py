"""Tests for AWEB_CUSTODY_KEY configuration and custodial agent signing."""

from __future__ import annotations

from uuid import UUID

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from beadhub.api import create_app

# 64 hex chars = 32 bytes, the required length for AES-256
VALID_CUSTODY_KEY = "a" * 64


@pytest.mark.asyncio
async def test_custody_key_enables_signing(monkeypatch, db_infra, redis_client_async):
    """When AWEB_CUSTODY_KEY is set, custodial agents get encrypted signing keys."""
    monkeypatch.setenv("AWEB_CUSTODY_KEY", VALID_CUSTODY_KEY)

    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            init = await client.post(
                "/v1/init",
                json={
                    "project_slug": "custody-test",
                    "alias": "custody-agent",
                    "agent_type": "agent",
                    "lifetime": "ephemeral",
                },
            )
            assert init.status_code == 200, init.text
            data = init.json()
            assert data["custody"] == "custodial"

            # Verify the agent has an encrypted signing key in the DB
            aweb_db = db_infra.get_manager("aweb")
            agent = await aweb_db.fetch_one(
                """
                SELECT signing_key_enc
                FROM {{tables.agents}}
                WHERE agent_id = $1 AND deleted_at IS NULL
                """,
                UUID(data["agent_id"]),
            )
            assert agent is not None
            assert agent["signing_key_enc"] is not None


@pytest.mark.asyncio
async def test_without_custody_key_no_signing(monkeypatch, db_infra, redis_client_async):
    """Without AWEB_CUSTODY_KEY, custodial agents have no signing key."""
    monkeypatch.delenv("AWEB_CUSTODY_KEY", raising=False)

    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            init = await client.post(
                "/v1/init",
                json={
                    "project_slug": "no-custody-test",
                    "alias": "no-custody-agent",
                    "agent_type": "agent",
                    "lifetime": "ephemeral",
                },
            )
            assert init.status_code == 200, init.text
            data = init.json()
            assert data["custody"] == "custodial"

            # Without AWEB_CUSTODY_KEY, signing key is discarded
            aweb_db = db_infra.get_manager("aweb")
            agent = await aweb_db.fetch_one(
                """
                SELECT signing_key_enc
                FROM {{tables.agents}}
                WHERE agent_id = $1 AND deleted_at IS NULL
                """,
                UUID(data["agent_id"]),
            )
            assert agent is not None
            assert agent["signing_key_enc"] is None
