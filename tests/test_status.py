import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from beadhub.api import create_app

TEST_REPO_ORIGIN = "git@github.com:anthropic/beadhub.git"


async def _init_project_auth(
    client: AsyncClient,
    *,
    project_slug: str,
    repo_origin: str,
    alias: str,
    human_name: str,
    role: str = "agent",
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
        json={"repo_origin": repo_origin, "role": role},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    data["api_key"] = api_key
    return data


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_status_endpoint_aggregates_state(db_infra, redis_client_async):
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            init = await _init_project_auth(
                client,
                project_slug="status-test",
                repo_origin="git@github.com:test/status.git",
                alias="frontend-bot",
                human_name="Test User",
            )
            client.headers.update(_auth_headers(init["api_key"]))

            # Register agents (presence)
            reg_payload = {
                "workspace_id": init["workspace_id"],
                "alias": "frontend-bot",  # ignored server-side but must validate as "alias"
                "program": "codex-cli",
                "model": "gpt-5.1",
            }
            resp = await client.post("/v1/agents/register", json=reg_payload)
            assert resp.status_code == 200

            # Create an escalation
            esc_payload = {
                "workspace_id": init["workspace_id"],
                "alias": "frontend-bot",
                "subject": "Need help",
                "situation": "Stuck on implementation.",
                "options": ["Keep waiting", "Switch issue"],
                "expires_in_hours": 1,
            }
            esc_resp = await client.post("/v1/escalations", json=esc_payload)
            assert esc_resp.status_code == 200

            # Fetch status
            status_resp = await client.get(
                "/v1/status", params={"workspace_id": init["workspace_id"]}
            )
            assert status_resp.status_code == 200
            data = status_resp.json()

            assert data["workspace"]["workspace_id"] == init["workspace_id"]
            assert data["workspace"]["project_id"] == init["project_id"]
            assert data["workspace"]["project_slug"] == init["project_slug"]
            assert "timestamp" in data

            agents = data["agents"]
            assert len(agents) == 1
            agent = agents[0]
            assert agent["alias"] == "frontend-bot"

            assert data["escalations_pending"] >= 1

            # Claims should be present (empty list initially)
            assert "claims" in data
            assert isinstance(data["claims"], list)


@pytest.mark.asyncio
async def test_status_includes_claims(db_infra, redis_client_async):
    """Status endpoint includes active claims for the workspace."""
    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            init = await _init_project_auth(
                client,
                project_slug=f"test-{uuid.uuid4().hex[:8]}",
                repo_origin=TEST_REPO_ORIGIN,
                alias="test-agent",
                human_name="Test User",
            )
            client.headers.update(_auth_headers(init["api_key"]))

            server_db = db_infra.get_manager("server")

            # Create a claim
            await server_db.execute(
                """
                INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
                VALUES ($1, $2, $3, $4, $5)
                """,
                uuid.UUID(init["project_id"]),
                uuid.UUID(init["workspace_id"]),
                "test-agent",
                "Test User",
                "bd-status-test",
            )

            resp = await client.get("/v1/status", params={"workspace_id": init["workspace_id"]})
            assert resp.status_code == 200
            data = resp.json()

            # Claims should include the created claim with claimant_count
            assert "claims" in data
            assert len(data["claims"]) == 1
            claim = data["claims"][0]
            assert claim["bead_id"] == "bd-status-test"
            assert claim["workspace_id"] == init["workspace_id"]
            assert claim["alias"] == "test-agent"
            assert claim["claimant_count"] == 1

            # No conflicts for single-claimant bead
            assert "conflicts" in data
            assert len(data["conflicts"]) == 0


@pytest.mark.asyncio
async def test_status_agents_include_enriched_fields(db_infra, redis_client_async):
    """Status endpoint agents list includes human_name, current_branch, canonical_origin, timezone."""
    from beadhub.presence import update_agent_presence

    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            init = await _init_project_auth(
                client,
                project_slug=f"test-{uuid.uuid4().hex[:8]}",
                repo_origin=TEST_REPO_ORIGIN,
                alias="enriched-agent",
                human_name="Alice Smith",
            )
            client.headers.update(_auth_headers(init["api_key"]))

            # Populate presence with all enriched fields
            await update_agent_presence(
                redis_client_async,
                workspace_id=init["workspace_id"],
                alias="enriched-agent",
                program="claude-code",
                model="claude-4",
                human_name="Alice Smith",
                project_id=init["project_id"],
                project_slug=init["project_slug"],
                repo_id=init["repo_id"],
                current_branch="feature/enrich",
                canonical_origin="github.com/anthropic/beadhub",
                timezone="Europe/Madrid",
            )

            resp = await client.get("/v1/status", params={"workspace_id": init["workspace_id"]})
            assert resp.status_code == 200
            data = resp.json()

            agents = data["agents"]
            assert len(agents) == 1
            agent = agents[0]
            assert agent["human_name"] == "Alice Smith"
            assert agent["current_branch"] == "feature/enrich"
            assert agent["canonical_origin"] == "github.com/anthropic/beadhub"
            assert agent["timezone"] == "Europe/Madrid"


@pytest.mark.asyncio
async def test_status_filters_by_repo_id(db_infra, redis_client_async):
    """Status endpoint filters workspaces by repo_id using secondary index."""
    from beadhub.presence import update_agent_presence

    project_slug = f"test-{uuid.uuid4().hex[:8]}"

    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            init = await _init_project_auth(
                client,
                project_slug=project_slug,
                repo_origin="git@github.com:test/repo-a.git",
                alias="agent-repo-a",
                human_name="User A",
            )
            client.headers.update(_auth_headers(init["api_key"]))
            project_id = uuid.UUID(init["project_id"])
            repo_id_1 = uuid.UUID(init["repo_id"])
            workspace_id_1 = init["workspace_id"]

            # Create a second workspace in the same project but a different repo.
            aweb_resp = await client.post(
                "/v1/init",
                json={
                    "project_slug": project_slug,
                    "project_name": project_slug,
                    "alias": "agent-repo-b",
                    "human_name": "User B",
                    "agent_type": "agent",
                },
            )
            assert aweb_resp.status_code == 200, aweb_resp.text
            api_key_b = aweb_resp.json()["api_key"]

            reg_b = await client.post(
                "/v1/workspaces/register",
                headers={"Authorization": f"Bearer {api_key_b}"},
                json={"repo_origin": "git@github.com:test/repo-b.git", "role": "agent"},
            )
            assert reg_b.status_code == 200, reg_b.text
            repo_id_2 = uuid.UUID(reg_b.json()["repo_id"])
            workspace_id_2 = reg_b.json()["workspace_id"]

    # Register presence for both workspaces with repo_id
    await update_agent_presence(
        redis_client_async,
        workspace_id_1,
        alias="agent-repo-a",
        program="test-cli",
        model="test-model",
        human_name="User A",
        project_id=str(project_id),
        project_slug=project_slug,
        repo_id=str(repo_id_1),
    )
    await update_agent_presence(
        redis_client_async,
        workspace_id_2,
        alias="agent-repo-b",
        program="test-cli",
        model="test-model",
        human_name="User B",
        project_id=str(project_id),
        project_slug=project_slug,
        repo_id=str(repo_id_2),
    )

    # Test the status endpoint with repo_id filter
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers.update(_auth_headers(init["api_key"]))
            # Filter by repo_id_1 - should only show agent-repo-a
            resp = await client.get("/v1/status", params={"repo_id": str(repo_id_1)})
            assert resp.status_code == 200
            data = resp.json()

            assert data["workspace"]["repo_id"] == str(repo_id_1)
            assert data["workspace"]["workspace_count"] == 1
            assert len(data["agents"]) == 1
            assert data["agents"][0]["alias"] == "agent-repo-a"

            # Filter by repo_id_2 - should only show agent-repo-b
            resp = await client.get("/v1/status", params={"repo_id": str(repo_id_2)})
            assert resp.status_code == 200
            data = resp.json()

            assert len(data["agents"]) == 1
            assert data["agents"][0]["alias"] == "agent-repo-b"


@pytest.mark.asyncio
async def test_status_shows_conflicts_for_multi_claim_beads(db_infra, redis_client_async):
    """Status endpoint shows conflicts when multiple workspaces claim the same bead."""
    workspace_id_1 = str(uuid.uuid4())
    workspace_id_2 = str(uuid.uuid4())

    server_db = db_infra.get_manager("server")

    app = create_app(db_infra=db_infra, redis=redis_client_async, serve_frontend=False)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            init = await _init_project_auth(
                client,
                project_slug=f"test-{uuid.uuid4().hex[:8]}",
                repo_origin=TEST_REPO_ORIGIN,
                alias="claude-main",
                human_name="Juan",
            )
            client.headers.update(_auth_headers(init["api_key"]))

            project_id = uuid.UUID(init["project_id"])
            repo_id = uuid.UUID(init["repo_id"])
            workspace_id_1 = init["workspace_id"]

            await server_db.execute(
                """
                INSERT INTO {{tables.workspaces}} (workspace_id, project_id, repo_id, alias, human_name)
                VALUES ($1, $2, $3, $4, $5)
                """,
                uuid.UUID(workspace_id_2),
                project_id,
                repo_id,
                "claude-fe",
                "Carlos",
            )

    # Create claims for both workspaces on the same bead (multi-claim scenario)
    await server_db.execute(
        """
        INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
        VALUES ($1, $2, $3, $4, $5)
        """,
        project_id,
        uuid.UUID(workspace_id_1),
        "claude-main",
        "Juan",
        "bd-shared-work",
    )
    await server_db.execute(
        """
        INSERT INTO {{tables.bead_claims}} (project_id, workspace_id, alias, human_name, bead_id)
        VALUES ($1, $2, $3, $4, $5)
        """,
        project_id,
        uuid.UUID(workspace_id_2),
        "claude-fe",
        "Carlos",
        "bd-shared-work",
    )

    # Test the status endpoint
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers.update(_auth_headers(init["api_key"]))
            # Query all claims (no workspace filter)
            resp = await client.get("/v1/status")
            assert resp.status_code == 200
            data = resp.json()

            # Both claims should be present with claimant_count = 2
            assert "claims" in data
            assert len(data["claims"]) == 2
            for claim in data["claims"]:
                assert claim["bead_id"] == "bd-shared-work"
                assert claim["claimant_count"] == 2

            # Conflicts should show this bead with both claimants
            assert "conflicts" in data
            assert len(data["conflicts"]) == 1
            conflict = data["conflicts"][0]
            assert conflict["bead_id"] == "bd-shared-work"
            assert len(conflict["claimants"]) == 2
            aliases = {c["alias"] for c in conflict["claimants"]}
            assert aliases == {"claude-main", "claude-fe"}
