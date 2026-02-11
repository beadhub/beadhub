"""Tests for the beads upload endpoint (POST /v1/beads/upload)."""

import base64
import json
import uuid
from datetime import datetime, timezone

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app

TEST_REDIS_URL = "redis://localhost:6379/15"


async def _init_project(client: AsyncClient, slug: str = "test-project") -> dict:
    """Create a project/agent/api_key in aweb, then register a BeadHub workspace."""
    alias = f"test-agent-{uuid.uuid4().hex[:8]}"
    repo_origin = f"git@github.com:test/{slug}.git"
    aweb_resp = await client.post(
        "/v1/init",
        json={
            "project_slug": slug,
            "project_name": slug,
            "alias": alias,
            "human_name": "Test User",
            "agent_type": "agent",
        },
    )
    assert aweb_resp.status_code == 200, f"Failed to init project: {aweb_resp.text}"
    aweb_data = aweb_resp.json()
    api_key = aweb_data["api_key"]
    assert api_key.startswith("aw_sk_")

    reg = await client.post(
        "/v1/workspaces/register",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"repo_origin": repo_origin, "role": "agent"},
    )
    assert reg.status_code == 200, f"Failed to register workspace: {reg.text}"
    data = reg.json()
    data["api_key"] = api_key
    return data


async def _ensure_project(client: AsyncClient, slug: str = "test-project") -> str:
    """Create a project via /v1/init, set client Bearer auth, and return project_id."""
    data = await _init_project(client, slug=slug)
    client.headers["Authorization"] = f"Bearer {data['api_key']}"
    return data["project_id"]


@pytest.mark.asyncio
async def test_beads_upload_syncs_issues(db_infra):
    """Upload endpoint accepts JSON payload and syncs issues to database."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)

                issues = [
                    {
                        "id": "bd-upload-1",
                        "title": "First uploaded issue",
                        "status": "open",
                        "priority": 1,
                        "issue_type": "task",
                        "created_by": "juan",
                    },
                    {
                        "id": "bd-upload-2",
                        "title": "Second uploaded issue",
                        "status": "open",
                        "priority": 2,
                        "issue_type": "bug",
                        "dependencies": [{"depends_on_id": "bd-upload-1", "type": "blocks"}],
                        "created_by": "maria",
                    },
                ]

                upload_resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "my-repo",
                        "branch": "feature/test",
                        "issues": issues,
                    },
                )
                assert upload_resp.status_code == 200
                upload_data = upload_resp.json()
                assert upload_data["issues_synced"] == 2
                assert upload_data["repo"] == "my-repo"
                assert upload_data["branch"] == "feature/test"

                issues_resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "my-repo", "branch": "feature/test"},
                )
                assert issues_resp.status_code == 200
                issues_data = issues_resp.json()
                assert issues_data["count"] == 2

                ids = {issue["bead_id"] for issue in issues_data["issues"]}
                assert ids == {"bd-upload-1", "bd-upload-2"}

                by_id = {issue["bead_id"]: issue for issue in issues_data["issues"]}
                assert by_id["bd-upload-1"]["created_by"] == "juan"
                assert by_id["bd-upload-2"]["created_by"] == "maria"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_requires_repo(db_infra):
    """Upload must specify repo name."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                upload_resp = await client.post(
                    "/v1/beads/upload",
                    json={"issues": [{"id": "bd-1", "title": "Test", "status": "open"}]},
                )
                assert upload_resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_uses_default_branch(db_infra):
    """Branch defaults to 'main' if not specified."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                upload_resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "my-repo",
                        "issues": [{"id": "bd-1", "title": "Test", "status": "open"}],
                    },
                )
                assert upload_resp.status_code == 200
                assert upload_resp.json()["branch"] == "main"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_validates_branch_name(db_infra):
    """Invalid branch names are rejected."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                upload_resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "my-repo",
                        "branch": "../../../etc/passwd",
                        "issues": [{"id": "bd-1", "title": "Test", "status": "open"}],
                    },
                )
                assert upload_resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_validates_bead_ids(db_infra):
    """Invalid bead IDs are skipped with warning (not rejected)."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                upload_resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "my-repo",
                        "issues": [
                            {"id": "valid-id", "title": "Valid", "status": "open"},
                            {"id": "../bad", "title": "Invalid", "status": "open"},
                        ],
                    },
                )
                assert upload_resp.status_code == 200
                assert upload_resp.json()["issues_synced"] == 1
    finally:
        await redis.flushdb()
        await redis.aclose()


# --- JSONL Upload Tests ---


@pytest.mark.asyncio
async def test_beads_upload_jsonl_syncs_issues(db_infra):
    """Upload-jsonl endpoint accepts raw JSONL and syncs issues to database."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                jsonl_content = """\
{"id": "bd-jsonl-1", "title": "First JSONL issue", "status": "open", "priority": 1, "issue_type": "task", "created_by": "alice"}
{"id": "bd-jsonl-2", "title": "Second JSONL issue", "status": "open", "priority": 2, "issue_type": "bug", "created_by": "bob"}
"""
                upload_resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "jsonl-repo", "branch": "feature/jsonl"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert upload_resp.status_code == 200
                upload_data = upload_resp.json()
                assert upload_data["issues_synced"] == 2
                assert upload_data["repo"] == "jsonl-repo"
                assert upload_data["branch"] == "feature/jsonl"

                issues_resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "jsonl-repo", "branch": "feature/jsonl"},
                )
                assert issues_resp.status_code == 200
                issues_data = issues_resp.json()
                assert issues_data["count"] == 2
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_uses_default_branch(db_infra):
    """Branch defaults to 'main' if not specified."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                jsonl_content = '{"id": "bd-1", "title": "Test", "status": "open"}\n'
                upload_resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "my-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert upload_resp.status_code == 200
                assert upload_resp.json()["branch"] == "main"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_requires_repo(db_infra):
    """Upload-jsonl must specify repo in query params."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                jsonl_content = '{"id": "bd-1", "title": "Test", "status": "open"}\n'
                upload_resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert upload_resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_handles_empty_lines(db_infra):
    """Empty lines in JSONL are skipped gracefully."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                jsonl_content = """\
{"id": "bd-1", "title": "First", "status": "open"}

{"id": "bd-2", "title": "Second", "status": "open"}

"""
                upload_resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "my-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert upload_resp.status_code == 200
                assert upload_resp.json()["issues_synced"] == 2
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_rejects_invalid_json_line(db_infra):
    """Invalid JSON line returns 400 error."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                jsonl_content = """\
{"id": "bd-1", "title": "Valid", "status": "open"}
not valid json
{"id": "bd-2", "title": "Also valid", "status": "open"}
"""
                upload_resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "my-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert upload_resp.status_code == 400
                assert "line 2" in upload_resp.json()["detail"].lower()
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_validates_branch_name(db_infra):
    """Invalid branch names are rejected."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                jsonl_content = '{"id": "bd-1", "title": "Test", "status": "open"}\n'
                upload_resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "my-repo", "branch": "../../../etc/passwd"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert upload_resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_empty_file(db_infra):
    """Empty JSONL file succeeds with zero issues."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                upload_resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "my-repo"},
                    content="\n\n\n",
                    headers={"Content-Type": "text/plain"},
                )
                assert upload_resp.status_code == 200
                assert upload_resp.json()["issues_synced"] == 0
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_rejects_malicious_repo_name(db_infra):
    """API should reject malicious repo names before they reach the database."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                malicious_repos = [
                    "'; DROP TABLE beads_issues;--",
                    "a/../../../etc/passwd",
                    "repo/../evil",
                    "$(whoami)",
                ]

                for malicious in malicious_repos:
                    resp = await client.post(
                        "/v1/beads/upload",
                        json={
                            "repo": malicious,
                            "issues": [{"id": "bd-test", "title": "test"}],
                        },
                    )
                    assert resp.status_code == 422, f"Should reject repo: {malicious!r}"
                    detail = resp.json()["detail"]
                    assert any("Invalid repository" in err["msg"] for err in detail)
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_rejects_malicious_repo_name(db_infra):
    """JSONL upload should reject malicious repo names."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "a/../../../etc"},
                    content='{"id": "bd-test", "title": "test"}',
                    headers={
                        "Content-Type": "text/plain",
                    },
                )
                assert resp.status_code == 422
                assert "Invalid repo" in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_rejects_overly_long_repo_name(db_infra):
    """Repo names exceeding 255 chars should be rejected."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                long_repo = "a" * 256
                resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": long_repo,
                        "issues": [{"id": "bd-test", "title": "test"}],
                    },
                )
                assert resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_rejects_overly_long_repo_name(db_infra):
    """JSONL upload should reject repo names exceeding 255 chars."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                long_repo = "a" * 256
                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": long_repo},
                    content='{"id": "bd-test", "title": "test"}',
                    headers={
                        "Content-Type": "text/plain",
                    },
                )
                assert resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_filter_by_created_by(db_infra):
    """GET /v1/beads/issues supports filtering by created_by."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "creator-filter-repo",
                        "issues": [
                            {
                                "id": "bd-creator-a",
                                "title": "A",
                                "status": "open",
                                "issue_type": "task",
                                "created_by": "alice",
                            },
                            {
                                "id": "bd-creator-b",
                                "title": "B",
                                "status": "open",
                                "issue_type": "task",
                                "created_by": "bob",
                            },
                        ],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "creator-filter-repo", "created_by": "alice"},
                )
                assert resp.status_code == 200
                data = resp.json()
                ids = {issue["bead_id"] for issue in data["issues"]}
                assert ids == {"bd-creator-a"}

                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "creator-filter-repo",
                        "issues": [
                            {
                                "id": "bd-creator-num",
                                "title": "C",
                                "status": "open",
                                "issue_type": "task",
                                "created_by": 123,
                            }
                        ],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "creator-filter-repo", "created_by": "123"},
                )
                assert resp.status_code == 200
                data = resp.json()
                ids = {issue["bead_id"] for issue in data["issues"]}
                assert "bd-creator-num" in ids
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_default_order_by_recent(db_infra):
    """GET /v1/beads/issues orders by most recent updated/synced first."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "order-repo",
                        "issues": [
                            {
                                "id": "bd-order-old",
                                "title": "Old",
                                "status": "open",
                                "issue_type": "task",
                                "updated_at": "2025-01-01T00:00:00Z",
                            },
                            {
                                "id": "bd-order-mid",
                                "title": "Mid",
                                "status": "open",
                                "issue_type": "task",
                                "updated_at": "2025-01-02T00:00:00Z",
                            },
                            {
                                "id": "bd-order-new",
                                "title": "New",
                                "status": "open",
                                "issue_type": "task",
                                "updated_at": "2025-01-03T00:00:00Z",
                            },
                        ],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "order-repo", "limit": 10},
                )
                assert resp.status_code == 200
                data = resp.json()
                ids = [issue["bead_id"] for issue in data["issues"]]
                assert ids[:3] == ["bd-order-new", "bd-order-mid", "bd-order-old"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
# --- Audit Log Tests ---


@pytest.mark.asyncio
async def test_beads_upload_records_project_id_in_audit_log(db_infra):
    """Upload endpoint must record project_id in audit_log details."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                project_id = await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "audit-test-repo",
                        "issues": [{"id": "bd-audit-1", "title": "Test", "status": "open"}],
                    },
                )

                server_db = db_infra.get_manager("server")
                row = await server_db.fetch_one(
                    """
                    SELECT details FROM {{tables.audit_log}}
                    WHERE event_type = 'beads_uploaded'
                    AND details->>'repo' = 'audit-test-repo'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )

                assert row is not None, "Audit log entry not found"
                details = (
                    row["details"]
                    if isinstance(row["details"], dict)
                    else json.loads(row["details"])
                )
                assert "project_id" in details, "project_id missing from audit_log details"
                assert details["project_id"] == project_id
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_records_project_id_in_audit_log(db_infra):
    """JSONL upload endpoint must record project_id in audit_log details."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                project_id = await _ensure_project(client)
                jsonl_content = (
                    '{"id": "bd-audit-jsonl-1", "title": "Test JSONL", "status": "open"}\n'
                )
                await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "audit-jsonl-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )

                server_db = db_infra.get_manager("server")
                row = await server_db.fetch_one(
                    """
                    SELECT details FROM {{tables.audit_log}}
                    WHERE event_type = 'beads_uploaded'
                    AND details->>'repo' = 'audit-jsonl-repo'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )

                assert row is not None, "Audit log entry not found"
                details = (
                    row["details"]
                    if isinstance(row["details"], dict)
                    else json.loads(row["details"])
                )
                assert "project_id" in details, "project_id missing from audit_log details"
                assert details["project_id"] == project_id
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_rejects_too_many_issues(db_infra):
    """JSONL upload endpoint rejects uploads exceeding MAX_ISSUES_COUNT."""
    from beadhub.routes.beads import MAX_ISSUES_COUNT

    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues_count = MAX_ISSUES_COUNT + 1
                jsonl_content = "\n".join(
                    f'{{"id": "bd-{i}", "title": "Issue {i}", "status": "open"}}'
                    for i in range(issues_count)
                )

                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "too-many-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert resp.status_code == 400
                assert "Too many issues" in resp.json()["detail"]
                assert str(MAX_ISSUES_COUNT) in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_rejects_deep_nesting(db_infra):
    """JSONL upload endpoint rejects issues with nesting exceeding MAX_JSON_DEPTH."""
    from beadhub.routes.beads import MAX_JSON_DEPTH

    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                nested = "leaf"
                for _ in range(MAX_JSON_DEPTH + 1):
                    nested = {"nested": nested}

                issue = {"id": "bd-deep", "title": "Deep Issue", "status": "open", "data": nested}
                jsonl_content = json.dumps(issue)

                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "deep-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert resp.status_code == 400
                detail = resp.json()["detail"]
                assert "nesting depth exceeds limit" in detail
                assert "line 1" in detail
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_depth_boundary(db_infra):
    """JSONL upload endpoint correctly handles depth boundary conditions."""
    from beadhub.routes.beads import MAX_JSON_DEPTH

    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)

                nested = "leaf"
                for _ in range(MAX_JSON_DEPTH - 2):
                    nested = {"n": nested}
                valid_issue = {
                    "id": "bd-boundary-valid",
                    "title": "Valid",
                    "status": "open",
                    "d": nested,
                }

                nested = "leaf"
                for _ in range(MAX_JSON_DEPTH - 1):
                    nested = {"n": nested}
                invalid_issue = {
                    "id": "bd-boundary-invalid",
                    "title": "Invalid",
                    "status": "open",
                    "d": nested,
                }

                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "boundary-repo"},
                    content=json.dumps(valid_issue),
                    headers={"Content-Type": "text/plain"},
                )
                assert resp.status_code == 200

                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "boundary-repo"},
                    content=json.dumps(invalid_issue),
                    headers={"Content-Type": "text/plain"},
                )
                assert resp.status_code == 400
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_mixed_nesting(db_infra):
    """JSONL upload endpoint handles mixed dict/list nesting correctly."""
    from beadhub.routes.beads import MAX_JSON_DEPTH

    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                nested: object = "leaf"
                for i in range(MAX_JSON_DEPTH - 2):
                    if i % 2 == 0:
                        nested = [nested]
                    else:
                        nested = {"item": nested}

                issue = {"id": "bd-mixed", "title": "Mixed", "status": "open", "data": nested}
                jsonl_content = json.dumps(issue)

                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "mixed-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert resp.status_code == 200
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_empty_containers(db_infra):
    """JSONL upload endpoint accepts empty dicts and lists."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issue = {
                    "id": "bd-empty",
                    "title": "Empty",
                    "status": "open",
                    "empty_dict": {},
                    "empty_list": [],
                }
                jsonl_content = json.dumps(issue)

                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "empty-repo"},
                    content=jsonl_content,
                    headers={"Content-Type": "text/plain"},
                )
                assert resp.status_code == 200
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_upload_jsonl_extremely_deep_nesting_no_crash(db_infra):
    """JSONL upload endpoint handles extremely deep nesting gracefully."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                depth = 15000
                nested_json = '{"a":' * depth + '"leaf"' + "}" * depth

                resp = await client.post(
                    "/v1/beads/upload-jsonl",
                    params={"repo": "dos-test-repo"},
                    content=nested_json,
                    headers={"Content-Type": "text/plain"},
                )
                assert resp.status_code == 400
                detail = resp.json()["detail"]
                assert "nesting" in detail.lower() or "recursion" in detail.lower()
    finally:
        await redis.flushdb()
        await redis.aclose()


# --- GET /v1/beads/issues/{bead_id} Tests ---


@pytest.mark.asyncio
async def test_get_issue_by_bead_id(db_infra):
    """GET /v1/beads/issues/{bead_id} returns a single issue by its bead_id."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "lookup-repo",
                        "issues": [
                            {
                                "id": "bd-lookup-1",
                                "title": "Target Issue",
                                "status": "open",
                                "priority": 1,
                            },
                            {
                                "id": "bd-lookup-2",
                                "title": "Other Issue",
                                "status": "open",
                                "priority": 2,
                            },
                        ],
                    },
                )

                resp = await client.get("/v1/beads/issues/bd-lookup-1")
                assert resp.status_code == 200
                issue = resp.json()
                assert issue["bead_id"] == "bd-lookup-1"
                assert issue["title"] == "Target Issue"
                assert issue["priority"] == 1
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_get_issue_by_bead_id_not_found(db_infra):
    """GET /v1/beads/issues/{bead_id} returns 404 for non-existent issue."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                resp = await client.get("/v1/beads/issues/bd-nonexistent")
                assert resp.status_code == 404
                assert "not found" in resp.json()["detail"].lower()
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_get_issue_by_bead_id_tenant_isolation(db_infra):
    """GET /v1/beads/issues/{bead_id} respects tenant isolation."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                project = await _init_project(client, slug="test-project")
                other_project = await _init_project(client, slug="other-project")

                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "isolation-repo",
                        "issues": [
                            {"id": "bd-isolated", "title": "Isolated Issue", "status": "open"}
                        ],
                    },
                    headers={"Authorization": f"Bearer {project['api_key']}"},
                )

                resp = await client.get(
                    "/v1/beads/issues/bd-isolated",
                    headers={
                        "Authorization": f"Bearer {other_project['api_key']}",
                    },
                )
                assert resp.status_code == 404, "Should not see issue from another tenant"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_get_issue_by_bead_id_across_repos(db_infra):
    """GET /v1/beads/issues/{bead_id} returns a match when same bead_id exists in multiple repos."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "repo-a",
                        "issues": [
                            {"id": "bd-multi", "title": "Issue in Repo A", "status": "open"}
                        ],
                    },
                )
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "repo-b",
                        "issues": [
                            {"id": "bd-multi", "title": "Issue in Repo B", "status": "closed"}
                        ],
                    },
                )

                resp = await client.get("/v1/beads/issues/bd-multi")
                assert resp.status_code == 200
                issue = resp.json()
                assert issue["bead_id"] == "bd-multi"
                assert issue["repo"] in ("repo-a", "repo-b")
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_issues_type_filter(db_infra):
    """Test that /v1/beads/issues supports filtering by issue type."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "issues-type-filter-repo",
                        "issues": [
                            {
                                "id": "bd-issues-bug",
                                "title": "A Bug",
                                "status": "open",
                                "issue_type": "bug",
                            },
                            {
                                "id": "bd-issues-feature",
                                "title": "A Feature",
                                "status": "open",
                                "issue_type": "feature",
                            },
                        ],
                    },
                )
                assert resp.status_code == 200

                resp = await client.get("/v1/beads/issues?type=bug")
                assert resp.status_code == 200
                data = resp.json()

                bug_issue = next(
                    (i for i in data["issues"] if i["bead_id"] == "bd-issues-bug"), None
                )
                assert bug_issue is not None
                assert bug_issue["type"] == "bug"

                feature_issue = next(
                    (i for i in data["issues"] if i["bead_id"] == "bd-issues-feature"), None
                )
                assert feature_issue is None

                resp = await client.get("/v1/beads/issues?type=invalid")
                assert resp.status_code == 422
    finally:
        await redis.flushdb()
        await redis.aclose()


# --- GET /v1/beads/issues/{bead_id} with repo/branch ---


@pytest.mark.asyncio
async def test_get_issue_by_bead_id_with_repo_and_branch(db_infra):
    """GET /v1/beads/issues/{bead_id}?repo=X&branch=Y does O(1) indexed lookup."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "repo-alpha",
                        "branch": "main",
                        "issues": [{"id": "bd-indexed", "title": "Alpha Issue", "status": "open"}],
                    },
                )
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "repo-beta",
                        "branch": "develop",
                        "issues": [{"id": "bd-indexed", "title": "Beta Issue", "status": "closed"}],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues/bd-indexed",
                    params={"repo": "repo-alpha", "branch": "main"},
                )
                assert resp.status_code == 200
                issue = resp.json()
                assert issue["bead_id"] == "bd-indexed"
                assert issue["repo"] == "repo-alpha"
                assert issue["branch"] == "main"
                assert issue["title"] == "Alpha Issue"

                resp = await client.get(
                    "/v1/beads/issues/bd-indexed",
                    params={"repo": "repo-beta", "branch": "develop"},
                )
                assert resp.status_code == 200
                issue = resp.json()
                assert issue["bead_id"] == "bd-indexed"
                assert issue["repo"] == "repo-beta"
                assert issue["branch"] == "develop"
                assert issue["title"] == "Beta Issue"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_get_issue_by_bead_id_with_repo_branch_not_found(db_infra):
    """GET /v1/beads/issues/{bead_id}?repo=X&branch=Y returns 404 if not found."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "my-repo",
                        "branch": "main",
                        "issues": [{"id": "bd-exists", "title": "Exists", "status": "open"}],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues/bd-exists",
                    params={"repo": "my-repo", "branch": "wrong-branch"},
                )
                assert resp.status_code == 404

                resp = await client.get(
                    "/v1/beads/issues/bd-exists",
                    params={"repo": "wrong-repo", "branch": "main"},
                )
                assert resp.status_code == 404
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_get_issue_by_bead_id_invalid_repo_branch_format(db_infra):
    """GET /v1/beads/issues/{bead_id} rejects invalid repo/branch format."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                resp = await client.get(
                    "/v1/beads/issues/bd-test",
                    params={"repo": "invalid repo!", "branch": "main"},
                )
                assert resp.status_code == 422
                assert "Invalid repo" in resp.json()["detail"]

                resp = await client.get(
                    "/v1/beads/issues/bd-test",
                    params={"repo": "valid-repo", "branch": "invalid branch!"},
                )
                assert resp.status_code == 422
                assert "Invalid branch name" in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


# --- Parent-child relationship tests ---


@pytest.mark.asyncio
async def test_beads_issues_includes_parent_id(db_infra):
    """GET /v1/beads/issues must include parent_id in response."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "parent-test-repo",
                        "issues": [
                            {
                                "id": "bd-parent-1",
                                "title": "Parent Issue",
                                "status": "open",
                                "issue_type": "epic",
                            }
                        ],
                    },
                )

                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "parent-test-repo",
                        "issues": [
                            {
                                "id": "bd-child-1",
                                "title": "Child Issue",
                                "status": "open",
                                "issue_type": "task",
                                "dependencies": [
                                    {"depends_on_id": "bd-parent-1", "type": "parent-child"}
                                ],
                            }
                        ],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "parent-test-repo"},
                )
                assert resp.status_code == 200
                data = resp.json()

                child = next((i for i in data["issues"] if i["bead_id"] == "bd-child-1"), None)
                assert child is not None, "Child issue not found"
                assert "parent_id" in child, "parent_id field missing from response"
                assert child["parent_id"] is not None, "parent_id should be set for child"
                assert child["parent_id"]["bead_id"] == "bd-parent-1"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_get_issue_by_bead_id_includes_parent_id(db_infra):
    """GET /v1/beads/issues/{bead_id} must include parent_id in response."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "parent-single-repo",
                        "issues": [
                            {
                                "id": "bd-parent-single",
                                "title": "Parent Issue",
                                "status": "open",
                                "issue_type": "epic",
                            }
                        ],
                    },
                )

                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "parent-single-repo",
                        "issues": [
                            {
                                "id": "bd-child-single",
                                "title": "Child Issue",
                                "status": "open",
                                "issue_type": "task",
                                "dependencies": [
                                    {"depends_on_id": "bd-parent-single", "type": "parent-child"}
                                ],
                            }
                        ],
                    },
                )

                resp = await client.get("/v1/beads/issues/bd-child-single")
                assert resp.status_code == 200
                issue = resp.json()

                assert "parent_id" in issue, "parent_id field missing from response"
                assert issue["parent_id"] is not None, "parent_id should be set for child"
                assert issue["parent_id"]["bead_id"] == "bd-parent-single"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_parent_id_null_when_no_parent(db_infra):
    """Issues without a parent should have parent_id = null in response."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "no-parent-repo",
                        "issues": [
                            {
                                "id": "bd-orphan",
                                "title": "Orphan Issue",
                                "status": "open",
                                "issue_type": "task",
                            }
                        ],
                    },
                )

                resp = await client.get("/v1/beads/issues/bd-orphan")
                assert resp.status_code == 200
                issue = resp.json()

                assert "parent_id" in issue, "parent_id field should always be present"
                assert issue["parent_id"] is None, "parent_id should be null for orphan issue"
    finally:
        await redis.flushdb()
        await redis.aclose()


# --- Optimistic Locking Tests ---


@pytest.mark.asyncio
async def test_beads_upload_detects_stale_update(db_infra):
    """Upload endpoint rejects stale updates when DB has newer updated_at."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                project_id = await _ensure_project(client)

                initial_time = "2025-01-01T10:00:00Z"
                resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "stale-test-repo",
                        "issues": [
                            {
                                "id": "bd-stale-1",
                                "title": "Initial Title",
                                "status": "open",
                                "updated_at": initial_time,
                            }
                        ],
                    },
                )
                assert resp.status_code == 200
                assert resp.json()["issues_synced"] == 1

                newer_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
                server_db = db_infra.get_manager("beads")
                await server_db.execute(
                    """
                    UPDATE {{tables.beads_issues}}
                    SET updated_at = $1, title = 'Concurrently Updated Title'
                    WHERE bead_id = 'bd-stale-1' AND project_id = $2
                    """,
                    newer_time,
                    uuid.UUID(project_id),
                )

                stale_resp = await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "stale-test-repo",
                        "issues": [
                            {
                                "id": "bd-stale-1",
                                "title": "Stale Title Should Not Win",
                                "status": "closed",
                                "updated_at": initial_time,
                            }
                        ],
                    },
                )
                assert stale_resp.status_code == 200
                data = stale_resp.json()

                assert "conflicts" in data, "Response should include conflicts list"
                assert "conflicts_count" in data, "Response should include conflicts_count"
                assert data["conflicts_count"] == 1
                assert "bd-stale-1" in data["conflicts"]

                row = await server_db.fetch_one(
                    """
                    SELECT title, status FROM {{tables.beads_issues}}
                    WHERE bead_id = 'bd-stale-1' AND project_id = $1
                    """,
                    uuid.UUID(project_id),
                )

                assert row is not None
                assert (
                    row["title"] == "Concurrently Updated Title"
                ), "Stale update should not overwrite"
                assert row["status"] == "open", "Stale update should not change status"
    finally:
        await redis.flushdb()
        await redis.aclose()


# --- Search Tests ---


@pytest.mark.asyncio
async def test_beads_issues_search_by_bead_id_prefix(db_infra):
    """GET /v1/beads/issues with q= matches bead_id prefix."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues = [
                    {"id": "bd-search-abc", "title": "Issue ABC", "status": "open"},
                    {"id": "bd-search-xyz", "title": "Issue XYZ", "status": "open"},
                    {"id": "bd-other-123", "title": "Other 123", "status": "open"},
                ]
                await client.post(
                    "/v1/beads/upload",
                    json={"repo": "search-repo", "issues": issues},
                )

                resp = await client.get("/v1/beads/issues", params={"q": "bd-search"})
                assert resp.status_code == 200
                data = resp.json()

                ids = {issue["bead_id"] for issue in data["issues"]}
                assert "bd-search-abc" in ids
                assert "bd-search-xyz" in ids
                assert "bd-other-123" not in ids
                assert data["count"] == 2
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_search_by_title_substring(db_infra):
    """GET /v1/beads/issues with q= matches title substring (case-insensitive)."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues = [
                    {"id": "bd-title-1", "title": "Fix Authentication Bug", "status": "open"},
                    {"id": "bd-title-2", "title": "Add Login Form", "status": "open"},
                    {"id": "bd-title-3", "title": "Update README", "status": "open"},
                ]
                await client.post(
                    "/v1/beads/upload",
                    json={"repo": "search-repo", "issues": issues},
                )

                resp = await client.get("/v1/beads/issues", params={"q": "auth"})
                assert resp.status_code == 200
                data = resp.json()

                assert data["count"] == 1
                assert data["issues"][0]["bead_id"] == "bd-title-1"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_search_combines_with_filters(db_infra):
    """GET /v1/beads/issues q= search combines with other filters using AND."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues = [
                    {"id": "bd-combo-1", "title": "Open Task One", "status": "open"},
                    {"id": "bd-combo-2", "title": "Open Task Two", "status": "open"},
                    {"id": "bd-combo-3", "title": "Closed Task", "status": "closed"},
                ]
                await client.post(
                    "/v1/beads/upload",
                    json={"repo": "search-repo", "issues": issues},
                )

                resp = await client.get(
                    "/v1/beads/issues", params={"q": "Task", "status": "closed"}
                )
                assert resp.status_code == 200
                data = resp.json()

                assert data["count"] == 1
                assert data["issues"][0]["bead_id"] == "bd-combo-3"
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_search_empty_q_returns_all(db_infra):
    """GET /v1/beads/issues with empty q= returns all issues (no search filter)."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues = [
                    {"id": "bd-empty-q-1", "title": "First Issue", "status": "open"},
                    {"id": "bd-empty-q-2", "title": "Second Issue", "status": "open"},
                ]
                await client.post(
                    "/v1/beads/upload",
                    json={"repo": "empty-q-repo", "issues": issues},
                )

                resp = await client.get(
                    "/v1/beads/issues", params={"q": "", "repo": "empty-q-repo"}
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 2
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_search_escapes_like_metacharacters(db_infra):
    """GET /v1/beads/issues with q= properly escapes LIKE metacharacters."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues = [
                    {"id": "bd-test_one", "title": "Test_underscore title", "status": "open"},
                    {"id": "bd-test1one", "title": "Test1underscore title", "status": "open"},
                    {"id": "bd-percent", "title": "100% complete", "status": "open"},
                    {"id": "bd-other", "title": "Totally unrelated", "status": "open"},
                ]
                await client.post(
                    "/v1/beads/upload",
                    json={"repo": "escape-repo", "issues": issues},
                )

                resp = await client.get(
                    "/v1/beads/issues", params={"q": "Test_", "repo": "escape-repo"}
                )
                assert resp.status_code == 200
                data = resp.json()

                ids = {issue["bead_id"] for issue in data["issues"]}
                assert "bd-test_one" in ids
                assert "bd-test1one" not in ids

                resp = await client.get(
                    "/v1/beads/issues", params={"q": "100%", "repo": "escape-repo"}
                )
                assert resp.status_code == 200
                data = resp.json()

                ids = {issue["bead_id"] for issue in data["issues"]}
                assert "bd-percent" in ids
                assert data["count"] == 1
    finally:
        await redis.flushdb()
        await redis.aclose()


# --- Pagination Tests ---


@pytest.mark.asyncio
async def test_beads_issues_pagination_basic(db_infra):
    """GET /v1/beads/issues supports cursor-based pagination."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "pagination-repo",
                        "issues": [
                            {
                                "id": f"bd-page-{i}",
                                "title": f"Issue {i}",
                                "status": "open",
                                "issue_type": "task",
                                "priority": 2,
                                "updated_at": f"2025-01-0{i + 1}T00:00:00Z",
                            }
                            for i in range(5)
                        ],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues", params={"repo": "pagination-repo", "limit": 2}
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 2
                assert data["has_more"] is True
                assert data["next_cursor"] is not None
                ids = [issue["bead_id"] for issue in data["issues"]]
                assert ids == ["bd-page-4", "bd-page-3"]

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "pagination-repo", "limit": 2, "cursor": data["next_cursor"]},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 2
                assert data["has_more"] is True
                ids = [issue["bead_id"] for issue in data["issues"]]
                assert ids == ["bd-page-2", "bd-page-1"]

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "pagination-repo", "limit": 2, "cursor": data["next_cursor"]},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 1
                assert data["has_more"] is False
                assert data["next_cursor"] is None
                ids = [issue["bead_id"] for issue in data["issues"]]
                assert ids == ["bd-page-0"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_pagination_with_filters(db_infra):
    """Pagination works correctly when combined with filters."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues = [
                    {
                        "id": "bd-filter-open-1",
                        "title": "Open 1",
                        "status": "open",
                        "issue_type": "task",
                        "priority": 2,
                        "updated_at": "2025-01-01T00:00:00Z",
                    },
                    {
                        "id": "bd-filter-open-2",
                        "title": "Open 2",
                        "status": "open",
                        "issue_type": "task",
                        "priority": 2,
                        "updated_at": "2025-01-02T00:00:00Z",
                    },
                    {
                        "id": "bd-filter-open-3",
                        "title": "Open 3",
                        "status": "open",
                        "issue_type": "task",
                        "priority": 2,
                        "updated_at": "2025-01-03T00:00:00Z",
                    },
                    {
                        "id": "bd-filter-closed-1",
                        "title": "Closed 1",
                        "status": "closed",
                        "issue_type": "task",
                        "priority": 2,
                        "updated_at": "2025-01-04T00:00:00Z",
                    },
                ]
                await client.post(
                    "/v1/beads/upload",
                    json={"repo": "filter-page-repo", "issues": issues},
                )

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "filter-page-repo", "status": "open", "limit": 2},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 2
                assert data["has_more"] is True
                ids = [issue["bead_id"] for issue in data["issues"]]
                assert ids == ["bd-filter-open-3", "bd-filter-open-2"]

                resp = await client.get(
                    "/v1/beads/issues",
                    params={
                        "repo": "filter-page-repo",
                        "status": "open",
                        "limit": 2,
                        "cursor": data["next_cursor"],
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 1
                assert data["has_more"] is False
                ids = [issue["bead_id"] for issue in data["issues"]]
                assert ids == ["bd-filter-open-1"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_pagination_invalid_cursor(db_infra):
    """Invalid cursor returns 422 error."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "any-repo", "cursor": "invalid-not-base64!!!"},
                )
                assert resp.status_code == 422
                assert "Invalid cursor" in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_pagination_empty_results(db_infra):
    """Pagination with no matching results returns empty list with has_more=False."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "nonexistent-repo-xyz", "limit": 10},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 0
                assert data["issues"] == []
                assert data["has_more"] is False
                assert data["next_cursor"] is None
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_pagination_exact_boundary(db_infra):
    """Pagination when limit exactly equals total results."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "exact-boundary-repo",
                        "issues": [
                            {
                                "id": f"bd-exact-{i}",
                                "title": f"Exact {i}",
                                "status": "open",
                                "priority": 2,
                                "updated_at": f"2025-01-0{i + 1}T00:00:00Z",
                            }
                            for i in range(3)
                        ],
                    },
                )

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "exact-boundary-repo", "limit": 3},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 3
                assert data["has_more"] is False
                assert data["next_cursor"] is None
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_pagination_incomplete_cursor(db_infra):
    """Cursor with missing fields returns 422 error."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                incomplete_cursor = base64.urlsafe_b64encode(
                    json.dumps({"sort_time": "2025-01-01T00:00:00Z", "priority": 2}).encode()
                ).decode()

                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "any-repo", "cursor": incomplete_cursor},
                )
                assert resp.status_code == 422
                assert "incomplete sort key" in resp.json()["detail"]
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_comma_separated_status_filter(db_infra):
    """Status filter supports comma-separated values for filtering multiple statuses."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)
                issues = [
                    {
                        "id": "bd-status-open",
                        "title": "Open issue",
                        "status": "open",
                        "priority": 1,
                    },
                    {
                        "id": "bd-status-progress",
                        "title": "In progress issue",
                        "status": "in_progress",
                        "priority": 2,
                    },
                    {
                        "id": "bd-status-closed",
                        "title": "Closed issue",
                        "status": "closed",
                        "priority": 3,
                    },
                ]
                await client.post(
                    "/v1/beads/upload",
                    json={"repo": "status-filter-repo", "issues": issues},
                )

                # Single status filter still works
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "status-filter-repo", "status": "open"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 1
                assert data["issues"][0]["bead_id"] == "bd-status-open"

                # Comma-separated status filter returns multiple statuses
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "status-filter-repo", "status": "open,in_progress"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 2
                ids = {issue["bead_id"] for issue in data["issues"]}
                assert ids == {"bd-status-open", "bd-status-progress"}

                # Spaces around commas are trimmed
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "status-filter-repo", "status": "open, in_progress"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 2
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest.mark.asyncio
async def test_beads_issues_status_filter_validation(db_infra):
    """Status filter rejects invalid status values."""
    redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await _ensure_project(client)

                # Invalid status value returns 422
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"status": "invalid_status"},
                )
                assert resp.status_code == 422
                assert "Invalid status" in resp.json()["detail"]

                # Invalid status in comma-separated list returns 422
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"status": "open,invalid"},
                )
                assert resp.status_code == 422
                assert "Invalid status" in resp.json()["detail"]

                # Empty status (whitespace only) returns all issues (no filter applied)
                await client.post(
                    "/v1/beads/upload",
                    json={
                        "repo": "status-test-repo",
                        "issues": [
                            {"id": "bd-test", "title": "Test", "status": "open", "priority": 1}
                        ],
                    },
                )
                resp = await client.get(
                    "/v1/beads/issues",
                    params={"repo": "status-test-repo", "status": "  ,  ,  "},
                )
                assert resp.status_code == 200
                # Empty status list after stripping means no filter applied
                assert resp.json()["count"] >= 1
    finally:
        await redis.flushdb()
        await redis.aclose()
