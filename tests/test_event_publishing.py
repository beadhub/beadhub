"""Tests for SSE event publishing from bead sync and upload endpoints."""

import asyncio
import json
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from beadhub.api import create_app

TEST_REPO_ORIGIN = "git@github.com:test/event-publishing.git"


def _jsonl(*rows: dict) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


async def _setup_project(client) -> tuple[str, str, str, str, str]:
    """Create project and register workspace.

    Returns (project_id, repo_id, workspace_id, api_key, alias).
    """
    project_slug = f"evpub-{uuid.uuid4().hex[:8]}"

    aweb_resp = await client.post(
        "/v1/init",
        json={
            "project_slug": project_slug,
            "project_name": project_slug,
            "alias": f"agent-{uuid.uuid4().hex[:8]}",
            "human_name": "Test Agent",
            "agent_type": "agent",
        },
    )
    assert aweb_resp.status_code == 200, aweb_resp.text
    api_key = aweb_resp.json()["api_key"]

    reg_resp = await client.post(
        "/v1/workspaces/register",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"repo_origin": TEST_REPO_ORIGIN, "role": "agent"},
    )
    assert reg_resp.status_code == 200, reg_resp.text
    data = reg_resp.json()
    return data["project_id"], data["repo_id"], data["workspace_id"], api_key, data["alias"]


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


# =============================================================================
# Claim events
# =============================================================================


@pytest.mark.asyncio
async def test_sync_publishes_bead_claimed_event(db_infra, redis_client_async):
    """Claiming a bead via sync publishes BeadClaimedEvent."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, _, workspace_id, api_key, _ = await _setup_project(client)

            pubsub = await _subscribe(redis_client_async, workspace_id)
            try:
                resp = await client.post(
                    "/v1/bdh/sync",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "workspace_id": workspace_id,
                        "alias": "test-agent",
                        "human_name": "Test Agent",
                        "repo_origin": TEST_REPO_ORIGIN,
                        "role": "agent",
                        "sync_mode": "full",
                        "issues_jsonl": _jsonl(
                            {"id": "bd-1", "title": "Test bead", "status": "in_progress"}
                        ),
                        "command_line": "update bd-1 --status in_progress",
                    },
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                claimed_events = [e for e in events if e["type"] == "bead.claimed"]
                assert (
                    len(claimed_events) == 1
                ), f"Expected 1 bead.claimed event, got {len(claimed_events)} in {events}"
                assert claimed_events[0]["bead_id"] == "bd-1"
                assert claimed_events[0]["workspace_id"] == workspace_id
                # Enrichment: title from DB, alias, and project_slug
                assert claimed_events[0]["title"] == "Test bead"
                assert claimed_events[0]["alias"] == "test-agent"
                assert claimed_events[0]["project_slug"] is not None
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


@pytest.mark.asyncio
async def test_sync_publishes_bead_unclaimed_event(db_infra, redis_client_async):
    """Closing a bead via sync publishes BeadUnclaimedEvent."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, _, workspace_id, api_key, _ = await _setup_project(client)
            headers = {"Authorization": f"Bearer {api_key}"}

            # First, claim a bead
            resp = await client.post(
                "/v1/bdh/sync",
                headers=headers,
                json={
                    "workspace_id": workspace_id,
                    "alias": "test-agent",
                    "human_name": "Test Agent",
                    "repo_origin": TEST_REPO_ORIGIN,
                    "role": "agent",
                    "sync_mode": "full",
                    "issues_jsonl": _jsonl(
                        {"id": "bd-1", "title": "Test bead", "status": "in_progress"}
                    ),
                    "command_line": "update bd-1 --status in_progress",
                },
            )
            assert resp.status_code == 200, resp.text

            # Now subscribe and close the bead
            pubsub = await _subscribe(redis_client_async, workspace_id)
            try:
                resp = await client.post(
                    "/v1/bdh/sync",
                    headers=headers,
                    json={
                        "workspace_id": workspace_id,
                        "alias": "test-agent",
                        "human_name": "Test Agent",
                        "repo_origin": TEST_REPO_ORIGIN,
                        "role": "agent",
                        "sync_mode": "incremental",
                        "changed_issues": _jsonl(
                            {"id": "bd-1", "title": "Test bead", "status": "closed"}
                        ),
                        "deleted_ids": [],
                        "command_line": "close bd-1",
                    },
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                unclaimed_events = [e for e in events if e["type"] == "bead.unclaimed"]
                assert (
                    len(unclaimed_events) == 1
                ), f"Expected 1 bead.unclaimed event, got {len(unclaimed_events)} in {events}"
                assert unclaimed_events[0]["bead_id"] == "bd-1"
                assert unclaimed_events[0]["workspace_id"] == workspace_id
                # Enrichment: title from DB and project_slug
                assert unclaimed_events[0]["title"] == "Test bead"
                assert unclaimed_events[0]["project_slug"] is not None
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


@pytest.mark.asyncio
async def test_sync_publishes_unclaimed_events_for_deleted_ids(db_infra, redis_client_async):
    """Deleting beads via deleted_ids publishes BeadUnclaimedEvent for each."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, _, workspace_id, api_key, _ = await _setup_project(client)
            headers = {"Authorization": f"Bearer {api_key}"}

            # Create two beads with claims
            resp = await client.post(
                "/v1/bdh/sync",
                headers=headers,
                json={
                    "workspace_id": workspace_id,
                    "alias": "test-agent",
                    "human_name": "Test Agent",
                    "repo_origin": TEST_REPO_ORIGIN,
                    "role": "agent",
                    "sync_mode": "full",
                    "issues_jsonl": _jsonl(
                        {"id": "bd-a", "title": "Bead A", "status": "in_progress"},
                        {"id": "bd-b", "title": "Bead B", "status": "in_progress"},
                    ),
                    "command_line": "update bd-a --status in_progress",
                },
            )
            assert resp.status_code == 200, resp.text

            # Claim bd-b too
            resp = await client.post(
                "/v1/bdh/sync",
                headers=headers,
                json={
                    "workspace_id": workspace_id,
                    "alias": "test-agent",
                    "human_name": "Test Agent",
                    "repo_origin": TEST_REPO_ORIGIN,
                    "role": "agent",
                    "sync_mode": "incremental",
                    "changed_issues": _jsonl(
                        {"id": "bd-b", "title": "Bead B", "status": "in_progress"},
                    ),
                    "deleted_ids": [],
                    "command_line": "update bd-b --status in_progress",
                },
            )
            assert resp.status_code == 200, resp.text

            # Subscribe, then delete both via deleted_ids
            pubsub = await _subscribe(redis_client_async, workspace_id)
            try:
                resp = await client.post(
                    "/v1/bdh/sync",
                    headers=headers,
                    json={
                        "workspace_id": workspace_id,
                        "alias": "test-agent",
                        "human_name": "Test Agent",
                        "repo_origin": TEST_REPO_ORIGIN,
                        "role": "agent",
                        "sync_mode": "incremental",
                        "changed_issues": "",
                        "deleted_ids": ["bd-a", "bd-b"],
                        "command_line": "list",
                    },
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                unclaimed_events = [e for e in events if e["type"] == "bead.unclaimed"]
                unclaimed_bead_ids = {e["bead_id"] for e in unclaimed_events}
                assert unclaimed_bead_ids == {
                    "bd-a",
                    "bd-b",
                }, f"Expected unclaimed events for bd-a and bd-b, got {unclaimed_bead_ids}"
                # Enrichment: titles pre-fetched before deletion
                for ue in unclaimed_events:
                    assert ue["title"] is not None, f"Expected title for {ue['bead_id']}"
                    assert ue["project_slug"] is not None
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


# =============================================================================
# Status change events
# =============================================================================


@pytest.mark.asyncio
async def test_sync_publishes_bead_status_changed_event(db_infra, redis_client_async):
    """Syncing a new bead publishes BeadStatusChangedEvent."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, _, workspace_id, api_key, _ = await _setup_project(client)

            pubsub = await _subscribe(redis_client_async, workspace_id)
            try:
                resp = await client.post(
                    "/v1/bdh/sync",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "workspace_id": workspace_id,
                        "alias": "test-agent",
                        "human_name": "Test Agent",
                        "repo_origin": TEST_REPO_ORIGIN,
                        "role": "agent",
                        "sync_mode": "full",
                        "issues_jsonl": _jsonl(
                            {"id": "bd-2", "title": "New bead", "status": "open"}
                        ),
                        "command_line": "list",
                    },
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                sc_events = [e for e in events if e["type"] == "bead.status_changed"]
                assert (
                    len(sc_events) == 1
                ), f"Expected 1 bead.status_changed event, got {len(sc_events)} in {events}"
                assert sc_events[0]["bead_id"] == "bd-2"
                assert sc_events[0]["old_status"] == ""
                assert sc_events[0]["new_status"] == "open"
                assert sc_events[0]["workspace_id"] == workspace_id
                # Enrichment: title from BeadStatusChange and alias
                assert sc_events[0]["title"] == "New bead"
                assert sc_events[0]["alias"] == "test-agent"
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


@pytest.mark.asyncio
async def test_beads_upload_publishes_bead_status_changed_event(db_infra, redis_client_async):
    """Uploading beads via /v1/beads/upload publishes BeadStatusChangedEvent."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, _, workspace_id, api_key, _ = await _setup_project(client)

            pubsub = await _subscribe(redis_client_async, workspace_id)
            try:
                resp = await client.post(
                    "/v1/beads/upload",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "repo": "github.com/test/event-publishing",
                        "issues": [{"id": "bd-3", "title": "Upload bead", "status": "open"}],
                    },
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub)
                sc_events = [e for e in events if e["type"] == "bead.status_changed"]
                assert (
                    len(sc_events) == 1
                ), f"Expected 1 bead.status_changed event, got {len(sc_events)} in {events}"
                assert sc_events[0]["bead_id"] == "bd-3"
                assert sc_events[0]["new_status"] == "open"
                assert sc_events[0]["workspace_id"] == workspace_id
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()


@pytest.mark.asyncio
async def test_sync_no_events_when_no_status_changes(db_infra, redis_client_async):
    """Syncing unchanged beads publishes no status change events."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, _, workspace_id, api_key, _ = await _setup_project(client)
            headers = {"Authorization": f"Bearer {api_key}"}

            # First sync to create the bead
            resp = await client.post(
                "/v1/bdh/sync",
                headers=headers,
                json={
                    "workspace_id": workspace_id,
                    "alias": "test-agent",
                    "human_name": "Test Agent",
                    "repo_origin": TEST_REPO_ORIGIN,
                    "role": "agent",
                    "sync_mode": "full",
                    "issues_jsonl": _jsonl({"id": "bd-4", "title": "Existing", "status": "open"}),
                    "command_line": "list",
                },
            )
            assert resp.status_code == 200, resp.text

            # Subscribe, then sync same data again (no changes)
            pubsub = await _subscribe(redis_client_async, workspace_id)
            try:
                resp = await client.post(
                    "/v1/bdh/sync",
                    headers=headers,
                    json={
                        "workspace_id": workspace_id,
                        "alias": "test-agent",
                        "human_name": "Test Agent",
                        "repo_origin": TEST_REPO_ORIGIN,
                        "role": "agent",
                        "sync_mode": "full",
                        "issues_jsonl": _jsonl(
                            {"id": "bd-4", "title": "Existing", "status": "open"}
                        ),
                        "command_line": "list",
                    },
                )
                assert resp.status_code == 200, resp.text

                events = await _collect_events(pubsub, first_timeout=0.5)
                sc_events = [e for e in events if e["type"] == "bead.status_changed"]
                assert len(sc_events) == 0, f"Expected no status_changed events, got {sc_events}"
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()
