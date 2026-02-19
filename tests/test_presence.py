"""Tests for presence module - Redis presence tracking and secondary indexes."""

import os
import uuid

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from beadhub.presence import (
    get_workspace_id_by_alias,
    get_workspace_ids_by_branch,
    get_workspace_ids_by_project_id,
    get_workspace_ids_by_project_slug,
    get_workspace_ids_by_repo_id,
    list_agent_presences,
    list_agent_presences_by_workspace_ids,
    update_agent_presence,
)

TEST_REDIS_URL = os.getenv("BEADHUB_TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest_asyncio.fixture
async def async_redis():
    """Async Redis client for presence tests."""
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis is not available")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


class TestGetWorkspaceIdsByProjectId:
    """Tests for get_workspace_ids_by_project_id function."""

    @pytest.mark.asyncio
    async def test_returns_workspace_ids_in_project(self, async_redis):
        """Should return all workspace_ids that belong to the project."""
        project_id = str(uuid.uuid4())
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())

        # Register two workspaces in the same project
        await update_agent_presence(
            async_redis, ws1, "agent-1", "claude-code", "claude-4", project_id=project_id
        )
        await update_agent_presence(
            async_redis, ws2, "agent-2", "claude-code", "claude-4", project_id=project_id
        )

        result = await get_workspace_ids_by_project_id(async_redis, project_id)

        assert set(result) == {ws1, ws2}

    @pytest.mark.asyncio
    async def test_filters_stale_entries(self, async_redis):
        """Should filter out workspace_ids whose presence has expired."""
        project_id = str(uuid.uuid4())
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        # Register active workspace with normal TTL
        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            project_id=project_id,
            ttl_seconds=300,
        )

        # Register stale workspace with very short TTL, then manually add to index
        # Simulate: presence expired but index entry remains
        idx_key = f"idx:project_workspaces:{project_id}"
        await async_redis.sadd(idx_key, ws_stale)

        result = await get_workspace_ids_by_project_id(async_redis, project_id)

        # Should only return the active workspace
        assert result == [ws_active]

    @pytest.mark.asyncio
    async def test_cleans_up_stale_entries_from_index(self, async_redis):
        """Should remove stale entries from the index during lookup."""
        project_id = str(uuid.uuid4())
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        # Register active workspace
        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            project_id=project_id,
        )

        # Add stale entry directly to index (no presence key)
        idx_key = f"idx:project_workspaces:{project_id}"
        await async_redis.sadd(idx_key, ws_stale)

        # Call function - should clean up stale entry
        await get_workspace_ids_by_project_id(async_redis, project_id)

        # Verify stale entry was removed from index
        members = await async_redis.smembers(idx_key)
        assert ws_stale not in members
        assert ws_active in members

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_workspaces(self, async_redis):
        """Should return empty list when project has no workspaces."""
        project_id = str(uuid.uuid4())

        result = await get_workspace_ids_by_project_id(async_redis, project_id)

        assert result == []


class TestGetWorkspaceIdsByRepoId:
    """Tests for get_workspace_ids_by_repo_id function."""

    @pytest.mark.asyncio
    async def test_returns_workspace_ids_in_repo(self, async_redis):
        """Should return all workspace_ids that belong to the repo."""
        repo_id = str(uuid.uuid4())
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())

        await update_agent_presence(
            async_redis, ws1, "agent-1", "claude-code", "claude-4", repo_id=repo_id
        )
        await update_agent_presence(
            async_redis, ws2, "agent-2", "claude-code", "claude-4", repo_id=repo_id
        )

        result = await get_workspace_ids_by_repo_id(async_redis, repo_id)

        assert set(result) == {ws1, ws2}

    @pytest.mark.asyncio
    async def test_filters_stale_entries(self, async_redis):
        """Should filter out workspace_ids whose presence has expired."""
        repo_id = str(uuid.uuid4())
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
        )

        # Add stale entry directly to index
        idx_key = f"idx:repo_workspaces:{repo_id}"
        await async_redis.sadd(idx_key, ws_stale)

        result = await get_workspace_ids_by_repo_id(async_redis, repo_id)

        assert result == [ws_active]

    @pytest.mark.asyncio
    async def test_cleans_up_stale_entries_from_index(self, async_redis):
        """Should remove stale entries from the index during lookup."""
        repo_id = str(uuid.uuid4())
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
        )

        idx_key = f"idx:repo_workspaces:{repo_id}"
        await async_redis.sadd(idx_key, ws_stale)

        await get_workspace_ids_by_repo_id(async_redis, repo_id)

        members = await async_redis.smembers(idx_key)
        assert ws_stale not in members
        assert ws_active in members


class TestGetWorkspaceIdsByBranch:
    """Tests for get_workspace_ids_by_branch function."""

    @pytest.mark.asyncio
    async def test_returns_workspace_ids_on_branch(self, async_redis):
        """Should return all workspace_ids on the specified branch."""
        repo_id = str(uuid.uuid4())
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws1,
            "agent-1",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
            current_branch="main",
        )
        await update_agent_presence(
            async_redis,
            ws2,
            "agent-2",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
            current_branch="main",
        )

        result = await get_workspace_ids_by_branch(async_redis, repo_id, "main")

        assert set(result) == {ws1, ws2}

    @pytest.mark.asyncio
    async def test_filters_stale_entries(self, async_redis):
        """Should filter out workspace_ids whose presence has expired."""
        repo_id = str(uuid.uuid4())
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
            current_branch="main",
        )

        idx_key = f"idx:branch_workspaces:{repo_id}:main"
        await async_redis.sadd(idx_key, ws_stale)

        result = await get_workspace_ids_by_branch(async_redis, repo_id, "main")

        assert result == [ws_active]

    @pytest.mark.asyncio
    async def test_cleans_up_stale_entries_from_index(self, async_redis):
        """Should remove stale entries from the index during lookup."""
        repo_id = str(uuid.uuid4())
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
            current_branch="main",
        )

        idx_key = f"idx:branch_workspaces:{repo_id}:main"
        await async_redis.sadd(idx_key, ws_stale)

        await get_workspace_ids_by_branch(async_redis, repo_id, "main")

        members = await async_redis.smembers(idx_key)
        assert ws_stale not in members
        assert ws_active in members

    @pytest.mark.asyncio
    async def test_different_branches_are_separate(self, async_redis):
        """Should not return workspaces on different branches."""
        repo_id = str(uuid.uuid4())
        ws_main = str(uuid.uuid4())
        ws_feature = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_main,
            "agent-main",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
            current_branch="main",
        )
        await update_agent_presence(
            async_redis,
            ws_feature,
            "agent-feature",
            "claude-code",
            "claude-4",
            repo_id=repo_id,
            current_branch="feature-x",
        )

        result_main = await get_workspace_ids_by_branch(async_redis, repo_id, "main")
        result_feature = await get_workspace_ids_by_branch(async_redis, repo_id, "feature-x")

        assert result_main == [ws_main]
        assert result_feature == [ws_feature]


class TestGetWorkspaceIdsByProjectSlug:
    """Tests for get_workspace_ids_by_project_slug function using secondary index."""

    @pytest.mark.asyncio
    async def test_returns_workspace_ids_with_matching_slug(self, async_redis):
        """Should return all workspace_ids that have the project_slug."""
        project_slug = "my-project"
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())

        await update_agent_presence(
            async_redis, ws1, "agent-1", "claude-code", "claude-4", project_slug=project_slug
        )
        await update_agent_presence(
            async_redis, ws2, "agent-2", "claude-code", "claude-4", project_slug=project_slug
        )

        result = await get_workspace_ids_by_project_slug(async_redis, project_slug)

        assert set(result) == {ws1, ws2}

    @pytest.mark.asyncio
    async def test_different_slugs_are_separate(self, async_redis):
        """Should not return workspaces with different project_slug."""
        ws_project_a = str(uuid.uuid4())
        ws_project_b = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_project_a,
            "agent-a",
            "claude-code",
            "claude-4",
            project_slug="project-a",
        )
        await update_agent_presence(
            async_redis,
            ws_project_b,
            "agent-b",
            "claude-code",
            "claude-4",
            project_slug="project-b",
        )

        result_a = await get_workspace_ids_by_project_slug(async_redis, "project-a")
        result_b = await get_workspace_ids_by_project_slug(async_redis, "project-b")

        assert result_a == [ws_project_a]
        assert result_b == [ws_project_b]

    @pytest.mark.asyncio
    async def test_filters_stale_entries(self, async_redis):
        """Should filter out workspace_ids whose presence has expired."""
        project_slug = "my-project"
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            project_slug=project_slug,
        )

        # Add stale entry directly to index (no presence key)
        idx_key = f"idx:project_slug_workspaces:{project_slug}"
        await async_redis.sadd(idx_key, ws_stale)

        result = await get_workspace_ids_by_project_slug(async_redis, project_slug)

        assert result == [ws_active]

    @pytest.mark.asyncio
    async def test_cleans_up_stale_entries_from_index(self, async_redis):
        """Should remove stale entries from the index during lookup."""
        project_slug = "my-project"
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_active,
            "agent-active",
            "claude-code",
            "claude-4",
            project_slug=project_slug,
        )

        idx_key = f"idx:project_slug_workspaces:{project_slug}"
        await async_redis.sadd(idx_key, ws_stale)

        await get_workspace_ids_by_project_slug(async_redis, project_slug)

        members = await async_redis.smembers(idx_key)
        assert ws_stale not in members
        assert ws_active in members

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_workspaces(self, async_redis):
        """Should return empty list when no workspaces have the slug."""
        result = await get_workspace_ids_by_project_slug(async_redis, "nonexistent")

        assert result == []


class TestListAgentPresences:
    """Tests for list_agent_presences function using secondary index."""

    @pytest.mark.asyncio
    async def test_returns_all_presences_without_filter(self, async_redis):
        """Should return all presences using all_workspaces index."""
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())

        await update_agent_presence(async_redis, ws1, "agent-1", "claude-code", "claude-4")
        await update_agent_presence(async_redis, ws2, "agent-2", "claude-code", "claude-4")

        result = await list_agent_presences(async_redis)

        workspace_ids = {p.get("workspace_id") for p in result}
        assert workspace_ids == {ws1, ws2}

    @pytest.mark.asyncio
    async def test_returns_single_presence_with_workspace_id(self, async_redis):
        """Should return only the specified workspace's presence."""
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())

        await update_agent_presence(async_redis, ws1, "agent-1", "claude-code", "claude-4")
        await update_agent_presence(async_redis, ws2, "agent-2", "claude-code", "claude-4")

        result = await list_agent_presences(async_redis, workspace_id=ws1)

        assert len(result) == 1
        assert result[0].get("workspace_id") == ws1

    @pytest.mark.asyncio
    async def test_filters_stale_entries_from_all_workspaces(self, async_redis):
        """Should filter out expired presences when listing all."""
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis, ws_active, "agent-active", "claude-code", "claude-4"
        )

        # Add stale entry directly to all_workspaces index
        idx_key = "idx:all_workspaces"
        await async_redis.sadd(idx_key, ws_stale)

        result = await list_agent_presences(async_redis)

        workspace_ids = {p.get("workspace_id") for p in result}
        assert workspace_ids == {ws_active}

    @pytest.mark.asyncio
    async def test_cleans_up_stale_entries_from_all_workspaces_index(self, async_redis):
        """Should remove stale entries from all_workspaces index during lookup."""
        ws_active = str(uuid.uuid4())
        ws_stale = str(uuid.uuid4())

        await update_agent_presence(
            async_redis, ws_active, "agent-active", "claude-code", "claude-4"
        )

        idx_key = "idx:all_workspaces"
        await async_redis.sadd(idx_key, ws_stale)

        await list_agent_presences(async_redis)

        members = await async_redis.smembers(idx_key)
        assert ws_stale not in members
        assert ws_active in members

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_presences(self, async_redis):
        """Should return empty list when no presences exist."""
        result = await list_agent_presences(async_redis)

        assert result == []


class TestRolePreservation:
    """Tests for role field preservation in presence updates."""

    @pytest.mark.asyncio
    async def test_role_is_stored_and_returned(self, async_redis):
        """Should store and return role from presence."""
        ws_id = str(uuid.uuid4())

        await update_agent_presence(
            async_redis, ws_id, "agent-1", "claude-code", "claude-4", role="Full Stack"
        )

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("role") == "full stack"

    @pytest.mark.asyncio
    async def test_role_preserved_when_not_provided(self, async_redis):
        """Should preserve existing role when new presence doesn't provide one."""
        ws_id = str(uuid.uuid4())

        # First update with role
        await update_agent_presence(
            async_redis, ws_id, "agent-1", "claude-code", "claude-4", role="Full Stack"
        )

        # Second update without role (simulates old client)
        await update_agent_presence(async_redis, ws_id, "agent-1", "claude-code", "claude-4")

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("role") == "full stack"

    @pytest.mark.asyncio
    async def test_role_can_be_updated(self, async_redis):
        """Should update role when new value is provided."""
        ws_id = str(uuid.uuid4())

        # First update with role
        await update_agent_presence(
            async_redis, ws_id, "agent-1", "claude-code", "claude-4", role="Backend"
        )

        # Second update with new role
        await update_agent_presence(
            async_redis, ws_id, "agent-1", "claude-code", "claude-4", role="Frontend"
        )

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("role") == "frontend"

    @pytest.mark.asyncio
    async def test_oversized_role_not_preserved(self, async_redis):
        """Should ignore oversized roles when provided."""
        ws_id = str(uuid.uuid4())

        oversized_role = "x" * 51  # Exceeds 50 char limit
        await update_agent_presence(
            async_redis, ws_id, "agent-1", "claude-code", "claude-4", role=oversized_role
        )

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("role") is None


class TestPresenceByWorkspaceIds:
    """Tests for list_agent_presences_by_workspace_ids helper."""

    @pytest.mark.asyncio
    async def test_returns_only_requested_presences(self, async_redis):
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())
        ws3 = str(uuid.uuid4())

        await update_agent_presence(async_redis, ws1, "agent-1", "claude-code", "claude-4")
        await update_agent_presence(async_redis, ws2, "agent-2", "claude-code", "claude-4")

        results = await list_agent_presences_by_workspace_ids(async_redis, [ws1, ws3])
        ids = {entry.get("workspace_id") for entry in results}

        assert ws1 in ids
        assert ws2 not in ids
        assert ws3 not in ids

    @pytest.mark.asyncio
    async def test_does_not_scan_global_index(self):
        class FakePipeline:
            def __init__(self, store):
                self._store = store
                self.keys: list[str] = []

            def hgetall(self, key):
                self.keys.append(key)
                return self

            async def execute(self):
                return [self._store.get(key, {}) for key in self.keys]

        class FakeRedis:
            def __init__(self, store):
                self._store = store
                self.last_pipeline = None

            def pipeline(self):
                self.last_pipeline = FakePipeline(self._store)
                return self.last_pipeline

            async def smembers(self, _key):
                raise AssertionError("smembers should not be called")

            async def scan(self, *_args, **_kwargs):
                raise AssertionError("scan should not be called")

        store = {
            "presence:ws-1": {"workspace_id": "ws-1"},
            "presence:ws-2": {"workspace_id": "ws-2"},
        }
        redis = FakeRedis(store)

        results = await list_agent_presences_by_workspace_ids(redis, ["ws-1", "ws-3"])
        ids = {entry.get("workspace_id") for entry in results}

        assert ids == {"ws-1"}
        assert redis.last_pipeline is not None
        assert redis.last_pipeline.keys == ["presence:ws-1", "presence:ws-3"]


class TestKeyCollisionResistance:
    """Tests for Redis key collision resistance.

    These tests verify that user-controlled values containing colons
    cannot create key collisions across different logical entities.
    """

    @pytest.mark.asyncio
    async def test_alias_with_colon_does_not_collide(self, async_redis):
        """Alias containing colon should not collide with different project/alias combo."""
        project_a = str(uuid.uuid4())
        project_b = str(uuid.uuid4())
        ws_a = str(uuid.uuid4())
        ws_b = str(uuid.uuid4())

        # Create workspace with alias containing colon
        # project_a + "xyz:def" should NOT collide with project_b + "def"
        await update_agent_presence(
            async_redis, ws_a, "xyz:def", "claude-code", "claude-4", project_id=project_a
        )
        await update_agent_presence(
            async_redis, ws_b, "def", "claude-code", "claude-4", project_id=project_b
        )

        # Each should resolve to its own workspace
        result_a = await get_workspace_id_by_alias(async_redis, project_a, "xyz:def")
        result_b = await get_workspace_id_by_alias(async_redis, project_b, "def")

        assert result_a == ws_a
        assert result_b == ws_b

    @pytest.mark.asyncio
    async def test_branch_with_colon_does_not_collide(self, async_redis):
        """Branch containing colon should not collide with different repo/branch combo."""
        repo_a = str(uuid.uuid4())
        repo_b = str(uuid.uuid4())
        ws_a = str(uuid.uuid4())
        ws_b = str(uuid.uuid4())

        # Create workspace on branch with colon
        await update_agent_presence(
            async_redis,
            ws_a,
            "agent-a",
            "claude-code",
            "claude-4",
            repo_id=repo_a,
            current_branch="feature:test",
        )
        await update_agent_presence(
            async_redis,
            ws_b,
            "agent-b",
            "claude-code",
            "claude-4",
            repo_id=repo_b,
            current_branch="test",
        )

        # Each should be in its own index
        result_a = await get_workspace_ids_by_branch(async_redis, repo_a, "feature:test")
        result_b = await get_workspace_ids_by_branch(async_redis, repo_b, "test")

        assert result_a == [ws_a]
        assert result_b == [ws_b]

    @pytest.mark.asyncio
    async def test_project_slug_with_colon_does_not_collide(self, async_redis):
        """Project slug containing colon should create distinct keys."""
        ws_a = str(uuid.uuid4())
        ws_b = str(uuid.uuid4())

        # Create workspaces with slugs that could collide without encoding
        await update_agent_presence(
            async_redis,
            ws_a,
            "agent-a",
            "claude-code",
            "claude-4",
            project_slug="my:project",
        )
        await update_agent_presence(
            async_redis,
            ws_b,
            "agent-b",
            "claude-code",
            "claude-4",
            project_slug="project",
        )

        # Each should be in its own index
        result_a = await get_workspace_ids_by_project_slug(async_redis, "my:project")
        result_b = await get_workspace_ids_by_project_slug(async_redis, "project")

        assert result_a == [ws_a]
        assert result_b == [ws_b]

    @pytest.mark.asyncio
    async def test_special_characters_in_alias_handled(self, async_redis):
        """Aliases with special characters should be handled safely."""
        project_id = str(uuid.uuid4())
        ws_id = str(uuid.uuid4())

        # Test various special characters that could cause issues
        special_alias = "agent/with:special%chars&more"
        await update_agent_presence(
            async_redis,
            ws_id,
            special_alias,
            "claude-code",
            "claude-4",
            project_id=project_id,
        )

        result = await get_workspace_id_by_alias(async_redis, project_id, special_alias)
        assert result == ws_id


class TestGetWorkspaceIdByAlias:
    """Tests for get_workspace_id_by_alias function."""

    @pytest.mark.asyncio
    async def test_returns_workspace_id_for_alias_in_project(self, async_redis):
        """Should return the workspace_id using the alias in the project."""
        project_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        alias = "my-agent"

        await update_agent_presence(
            async_redis,
            workspace_id,
            alias,
            "claude-code",
            "claude-4",
            project_id=project_id,
        )

        result = await get_workspace_id_by_alias(async_redis, project_id, alias)
        assert result == workspace_id

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_alias(self, async_redis):
        """Should return None when alias doesn't exist in project."""
        project_id = str(uuid.uuid4())

        result = await get_workspace_id_by_alias(async_redis, project_id, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_different_projects_have_separate_aliases(self, async_redis):
        """Same alias in different projects should be separate."""
        project_a = str(uuid.uuid4())
        project_b = str(uuid.uuid4())
        ws_a = str(uuid.uuid4())
        ws_b = str(uuid.uuid4())
        alias = "shared-alias"

        await update_agent_presence(
            async_redis, ws_a, alias, "claude-code", "claude-4", project_id=project_a
        )
        await update_agent_presence(
            async_redis, ws_b, alias, "claude-code", "claude-4", project_id=project_b
        )

        result_a = await get_workspace_id_by_alias(async_redis, project_a, alias)
        result_b = await get_workspace_id_by_alias(async_redis, project_b, alias)

        assert result_a == ws_a
        assert result_b == ws_b

    @pytest.mark.asyncio
    async def test_filters_stale_index_entries(self, async_redis):
        """Should return None and cleanup when index exists but presence expired."""
        project_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        alias = "stale-agent"

        # Create stale index entry directly (no presence key)
        idx_key = f"idx:alias:{project_id}:{alias}"
        await async_redis.set(idx_key, workspace_id)

        result = await get_workspace_id_by_alias(async_redis, project_id, alias)

        assert result is None
        # Index entry should be cleaned up
        assert await async_redis.get(idx_key) is None

    @pytest.mark.asyncio
    async def test_alias_index_updated_on_presence_refresh(self, async_redis):
        """Alias index should be updated when presence is refreshed."""
        project_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        alias = "my-agent"

        # First presence update
        await update_agent_presence(
            async_redis,
            workspace_id,
            alias,
            "claude-code",
            "claude-4",
            project_id=project_id,
        )

        # Refresh presence with same alias
        await update_agent_presence(
            async_redis,
            workspace_id,
            alias,
            "claude-code",
            "claude-4",
            project_id=project_id,
        )

        result = await get_workspace_id_by_alias(async_redis, project_id, alias)
        assert result == workspace_id


class TestTimezoneAndCanonicalOrigin:
    """Tests for timezone and canonical_origin fields in presence."""

    @pytest.mark.asyncio
    async def test_canonical_origin_stored_and_returned(self, async_redis):
        """Should store and return canonical_origin from presence."""
        ws_id = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_id,
            "agent-1",
            "claude-code",
            "claude-4",
            canonical_origin="github.com/org/repo",
        )

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("canonical_origin") == "github.com/org/repo"

    @pytest.mark.asyncio
    async def test_canonical_origin_preserved_when_not_provided(self, async_redis):
        """Should preserve existing canonical_origin when new presence doesn't provide one."""
        ws_id = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_id,
            "agent-1",
            "claude-code",
            "claude-4",
            canonical_origin="github.com/org/repo",
        )

        # Second update without canonical_origin
        await update_agent_presence(
            async_redis,
            ws_id,
            "agent-1",
            "claude-code",
            "claude-4",
        )

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("canonical_origin") == "github.com/org/repo"

    @pytest.mark.asyncio
    async def test_timezone_stored_and_returned(self, async_redis):
        """Should store and return timezone from presence."""
        ws_id = str(uuid.uuid4())

        await update_agent_presence(
            async_redis,
            ws_id,
            "agent-1",
            "claude-code",
            "claude-4",
            timezone="Europe/Madrid",
        )

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("timezone") == "Europe/Madrid"

    @pytest.mark.asyncio
    async def test_timezone_preserved_when_not_provided(self, async_redis):
        """Should preserve existing timezone when new presence doesn't provide one."""
        ws_id = str(uuid.uuid4())

        # First update with timezone
        await update_agent_presence(
            async_redis,
            ws_id,
            "agent-1",
            "claude-code",
            "claude-4",
            timezone="America/New_York",
        )

        # Second update without timezone (simulates old client)
        await update_agent_presence(
            async_redis,
            ws_id,
            "agent-1",
            "claude-code",
            "claude-4",
        )

        result = await list_agent_presences(async_redis, workspace_id=ws_id)
        assert len(result) == 1
        assert result[0].get("timezone") == "America/New_York"
