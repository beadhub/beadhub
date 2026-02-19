"""Tests for SSE events published via aweb mutation hooks (Phase 2).

These test that mail, chat, and reservation mutations in aweb
trigger SSE events via the on_mutation callback registered by beadhub.
"""

import asyncio
import json
import logging
import uuid
from unittest.mock import MagicMock

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from beadhub.api import create_app
from beadhub.mutation_hooks import _translate, create_mutation_handler


async def _collect_events(pubsub, max_events=10, first_timeout=2.0, next_timeout=0.2):
    """Collect events from pubsub. Waits longer for first, shorter for subsequent."""
    events = []
    await asyncio.sleep(0.1)
    timeout = first_timeout
    for _ in range(max_events):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if msg is None:
            break
        if msg["type"] == "message":
            events.append(json.loads(msg["data"]))
        timeout = next_timeout
    return events


async def _subscribe(redis, workspace_id):
    """Subscribe to workspace event channel, consuming the confirmation."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"events:{workspace_id}")
    msg = await pubsub.get_message(timeout=1.0)
    assert msg is not None and msg["type"] == "subscribe"
    return pubsub


async def _setup_two_agents(client):
    """Create a project with two agents. Returns (ws_a, key_a, ws_b, key_b).

    Also sends a heartbeat for each agent to populate Redis presence,
    which is needed for event enrichment (alias lookups).
    """
    project_slug = f"mhook-{uuid.uuid4().hex[:8]}"
    repo_origin = f"git@github.com:test/mutation-hooks-{project_slug}.git"

    # Agent A
    resp_a = await client.post(
        "/v1/init",
        json={
            "project_slug": project_slug,
            "project_name": project_slug,
            "alias": f"agent-a-{uuid.uuid4().hex[:4]}",
            "human_name": "Agent A",
            "agent_type": "agent",
        },
    )
    assert resp_a.status_code == 200, resp_a.text
    key_a = resp_a.json()["api_key"]

    reg_a = await client.post(
        "/v1/workspaces/register",
        headers={"Authorization": f"Bearer {key_a}"},
        json={"repo_origin": repo_origin, "role": "agent"},
    )
    assert reg_a.status_code == 200, reg_a.text
    ws_a = reg_a.json()["workspace_id"]
    alias_a = reg_a.json()["alias"]

    # Heartbeat A to populate Redis presence
    hb_a = await client.post(
        "/v1/workspaces/heartbeat",
        headers={"Authorization": f"Bearer {key_a}"},
        json={"workspace_id": ws_a, "alias": alias_a, "repo_origin": repo_origin},
    )
    assert hb_a.status_code == 200, hb_a.text

    # Agent B
    resp_b = await client.post(
        "/v1/init",
        json={
            "project_slug": project_slug,
            "project_name": project_slug,
            "alias": f"agent-b-{uuid.uuid4().hex[:4]}",
            "human_name": "Agent B",
            "agent_type": "agent",
        },
    )
    assert resp_b.status_code == 200, resp_b.text
    key_b = resp_b.json()["api_key"]

    reg_b = await client.post(
        "/v1/workspaces/register",
        headers={"Authorization": f"Bearer {key_b}"},
        json={"repo_origin": repo_origin, "role": "agent"},
    )
    assert reg_b.status_code == 200, reg_b.text
    ws_b = reg_b.json()["workspace_id"]
    alias_b = reg_b.json()["alias"]

    # Heartbeat B to populate Redis presence
    hb_b = await client.post(
        "/v1/workspaces/heartbeat",
        headers={"Authorization": f"Bearer {key_b}"},
        json={"workspace_id": ws_b, "alias": alias_b, "repo_origin": repo_origin},
    )
    assert hb_b.status_code == 200, hb_b.text

    return ws_a, key_a, alias_a, ws_b, key_b, alias_b


# =============================================================================
# Mail events
# =============================================================================


@pytest.mark.asyncio
async def test_message_sent_publishes_event(db_infra, redis_client_async):
    """Sending a message publishes MessageDeliveredEvent to recipient's channel."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ws_a, key_a, alias_a, ws_b, _, alias_b = await _setup_two_agents(client)

            # Subscribe to recipient's channel
            pubsub = await _subscribe(redis_client_async, ws_b)
            try:
                resp = await client.post(
                    "/v1/messages",
                    headers={"Authorization": f"Bearer {key_a}"},
                    json={
                        "to_alias": alias_b,
                        "subject": "Test subject",
                        "body": "Hello from agent A",
                    },
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                msg_events = [e for e in events if e["type"] == "message.delivered"]
                assert len(msg_events) == 1, f"Expected 1 message.delivered event, got {msg_events}"
                assert msg_events[0]["workspace_id"] == ws_b
                assert msg_events[0]["subject"] == "Test subject"
                # Enrichment: aliases resolved from presence
                assert msg_events[0]["from_alias"] == alias_a
                assert msg_events[0]["to_alias"] == alias_b
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


@pytest.mark.asyncio
async def test_message_ack_publishes_event(db_infra, redis_client_async):
    """Acknowledging a message publishes MessageAcknowledgedEvent."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, key_a, alias_a, ws_b, key_b, alias_b = await _setup_two_agents(client)

            # Send a message from A to B with a subject
            send_resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {key_a}"},
                json={"to_alias": alias_b, "subject": "Ack subject", "body": "Ack test"},
            )
            assert send_resp.status_code == 200, send_resp.text
            message_id = send_resp.json()["message_id"]

            # Subscribe to B's channel, then ack
            pubsub = await _subscribe(redis_client_async, ws_b)
            try:
                resp = await client.post(
                    f"/v1/messages/{message_id}/ack",
                    headers={"Authorization": f"Bearer {key_b}"},
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                ack_events = [e for e in events if e["type"] == "message.acknowledged"]
                assert (
                    len(ack_events) == 1
                ), f"Expected 1 message.acknowledged event, got {ack_events}"
                assert ack_events[0]["message_id"] == message_id
                assert ack_events[0]["workspace_id"] == ws_b
                # Enrichment: from_alias and subject from original message
                assert ack_events[0]["from_alias"] == alias_a
                assert ack_events[0]["subject"] == "Ack subject"
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


# =============================================================================
# Chat events
# =============================================================================


@pytest.mark.asyncio
async def test_chat_message_publishes_event(db_infra, redis_client_async):
    """Sending a chat message publishes ChatMessageEvent to sender's channel."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ws_a, key_a, alias_a, _, _, alias_b = await _setup_two_agents(client)

            # Subscribe to sender's channel
            pubsub = await _subscribe(redis_client_async, ws_a)
            try:
                resp = await client.post(
                    "/v1/chat/sessions",
                    headers={"Authorization": f"Bearer {key_a}"},
                    json={
                        "to_aliases": [alias_b],
                        "message": "Hey, can we talk?",
                    },
                )
                assert resp.status_code == 200, resp.text
                session_id = resp.json()["session_id"]

                events = await _collect_events(pubsub)
                chat_events = [e for e in events if e["type"] == "chat.message_sent"]
                assert (
                    len(chat_events) == 1
                ), f"Expected 1 chat.message_sent event, got {chat_events}"
                assert chat_events[0]["session_id"] == session_id
                assert chat_events[0]["workspace_id"] == ws_a
                # Enrichment: aliases and preview from DB lookups
                assert chat_events[0]["from_alias"] == alias_a
                assert alias_b in chat_events[0]["to_aliases"]
                assert chat_events[0]["preview"] == "Hey, can we talk?"
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


# =============================================================================
# Reservation events
# =============================================================================


@pytest.mark.asyncio
async def test_reservation_acquired_publishes_event(db_infra, redis_client_async):
    """Acquiring a reservation publishes ReservationAcquiredEvent."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ws_a, key_a, alias_a, _, _, _ = await _setup_two_agents(client)

            pubsub = await _subscribe(redis_client_async, ws_a)
            try:
                resp = await client.post(
                    "/v1/reservations",
                    headers={"Authorization": f"Bearer {key_a}"},
                    json={"resource_key": "src/main.py", "ttl_seconds": 120},
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                res_events = [e for e in events if e["type"] == "reservation.acquired"]
                assert (
                    len(res_events) == 1
                ), f"Expected 1 reservation.acquired event, got {res_events}"
                assert res_events[0]["workspace_id"] == ws_a
                assert "src/main.py" in res_events[0]["paths"]
                # Enrichment: alias resolved from presence
                assert res_events[0]["alias"] == alias_a
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


@pytest.mark.asyncio
async def test_reservation_released_publishes_event(db_infra, redis_client_async):
    """Releasing a reservation publishes ReservationReleasedEvent."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ws_a, key_a, alias_a, _, _, _ = await _setup_two_agents(client)

            # Acquire first
            resp = await client.post(
                "/v1/reservations",
                headers={"Authorization": f"Bearer {key_a}"},
                json={"resource_key": "src/util.py", "ttl_seconds": 120},
            )
            assert resp.status_code == 200, resp.text

            # Subscribe, then release
            pubsub = await _subscribe(redis_client_async, ws_a)
            try:
                resp = await client.post(
                    "/v1/reservations/release",
                    headers={"Authorization": f"Bearer {key_a}"},
                    json={"resource_key": "src/util.py"},
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                rel_events = [e for e in events if e["type"] == "reservation.released"]
                assert (
                    len(rel_events) == 1
                ), f"Expected 1 reservation.released event, got {rel_events}"
                assert rel_events[0]["workspace_id"] == ws_a
                assert "src/util.py" in rel_events[0]["paths"]
                # Enrichment: alias resolved from presence
                assert rel_events[0]["alias"] == alias_a
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


# =============================================================================
# Unit tests for _translate
# =============================================================================


def test_translate_unknown_event_type_returns_none():
    """Unknown aweb event types are safely ignored."""
    assert _translate("foo.bar", {}) is None
    assert _translate("reservation.renew", {"resource_key": "x"}) is None


def test_translate_missing_workspace_id_produces_empty():
    """Missing agent_id fields produce events with empty workspace_id."""
    event = _translate("message.sent", {"message_id": "m1", "subject": "hi"})
    assert event is not None
    assert event.workspace_id == ""


def test_translate_message_sent_maps_fields():
    """message.sent context maps correctly to MessageDeliveredEvent."""
    event = _translate(
        "message.sent",
        {
            "message_id": "m1",
            "from_agent_id": "agent-a",
            "to_agent_id": "agent-b",
            "subject": "hello",
        },
    )
    assert event.type == "message.delivered"
    assert event.workspace_id == "agent-b"
    assert event.from_workspace == "agent-a"
    assert event.message_id == "m1"
    assert event.subject == "hello"
    # Enrichment fields default to empty before async enrichment
    assert event.to_alias == ""
    assert event.from_alias == ""


def test_translate_message_ack_defaults_enrichment_fields():
    """message.acknowledged has empty enrichment fields before async enrichment."""
    event = _translate(
        "message.acknowledged",
        {"agent_id": "agent-b", "message_id": "m1"},
    )
    assert event.type == "message.acknowledged"
    assert event.from_alias == ""
    assert event.subject == ""


def test_translate_chat_message_defaults_enrichment_fields():
    """chat.message_sent has empty enrichment fields before async enrichment."""
    event = _translate(
        "chat.message_sent",
        {"from_agent_id": "agent-a", "session_id": "s1", "message_id": "m1"},
    )
    assert event.type == "chat.message_sent"
    assert event.from_alias == ""
    assert event.to_aliases == []
    assert event.preview == ""


def test_translate_reservation_acquired_alias_defaults_empty():
    """reservation.acquired alias defaults to empty before async enrichment."""
    event = _translate(
        "reservation.acquired",
        {"holder_agent_id": "agent-a", "resource_key": "src/main.py", "ttl_seconds": 120},
    )
    assert event.type == "reservation.acquired"
    assert event.alias == ""


# =============================================================================
# Enrichment failure resilience
# =============================================================================


@pytest.mark.asyncio
async def test_on_mutation_publishes_event_when_enrichment_fails(redis_client_async, caplog):
    """Events are still published when enrichment fails (e.g., transient DB error)."""
    broken_db_infra = MagicMock()
    broken_db_infra.get_manager.side_effect = RuntimeError("DB connection lost")

    handler = create_mutation_handler(redis_client_async, broken_db_infra)

    pubsub = await _subscribe(redis_client_async, "agent-b")
    try:
        # message.acknowledged with a message_id triggers DB enrichment,
        # which will fail due to broken db_infra
        with caplog.at_level(logging.WARNING, logger="beadhub.mutation_hooks"):
            await handler(
                "message.acknowledged",
                {"agent_id": "agent-b", "message_id": str(uuid.uuid4())},
            )

        events = await _collect_events(pubsub)
        ack_events = [e for e in events if e["type"] == "message.acknowledged"]
        assert len(ack_events) == 1, "Event should be published even when enrichment fails"
        assert ack_events[0]["workspace_id"] == "agent-b"
        # Enrichment fields should have defaults (enrichment failed)
        assert ack_events[0]["from_alias"] == ""
        assert ack_events[0]["subject"] == ""

        # Enrichment failure should be logged as a warning
        enrichment_warnings = [r for r in caplog.records if "Enrichment failed" in r.message]
        assert len(enrichment_warnings) == 1
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()
