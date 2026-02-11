"""Tests for app lifespan cleanup on initialization failure."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestStandaloneLifespanCleanup:
    """Tests for _make_standalone_lifespan cleanup behavior."""

    @pytest.mark.asyncio
    async def test_redis_closed_when_db_init_fails(self):
        """When database initialization fails, Redis should be closed."""
        from beadhub.api import _make_standalone_lifespan

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()

        class MockState:
            pass

        class MockApp:
            state = MockState()

        app = MockApp()

        async def mock_redis_from_url(*args, **kwargs):
            return mock_redis

        with (
            patch("beadhub.api.async_redis_from_url", side_effect=mock_redis_from_url),
            patch("beadhub.api.default_db_infra") as mock_db_infra,
            patch("beadhub.api.get_settings") as mock_settings,
            patch("beadhub.api.configure_logging"),
        ):
            mock_settings.return_value.redis_url = "redis://localhost:6379"
            mock_settings.return_value.log_level = "info"
            mock_db_infra.initialize = AsyncMock(side_effect=Exception("DB connection failed"))

            lifespan = _make_standalone_lifespan()

            with pytest.raises(Exception, match="DB connection failed"):
                async with lifespan(app):
                    pass

            # Redis should be closed on failure
            mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_state_not_set_when_db_init_fails(self):
        """When database initialization fails, app.state should not have partial state."""
        from beadhub.api import _make_standalone_lifespan

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()

        class MockState:
            pass

        class MockApp:
            state = MockState()

        app = MockApp()

        async def mock_redis_from_url(*args, **kwargs):
            return mock_redis

        with (
            patch("beadhub.api.async_redis_from_url", side_effect=mock_redis_from_url),
            patch("beadhub.api.default_db_infra") as mock_db_infra,
            patch("beadhub.api.get_settings") as mock_settings,
            patch("beadhub.api.configure_logging"),
        ):
            mock_settings.return_value.redis_url = "redis://localhost:6379"
            mock_settings.return_value.log_level = "info"
            mock_db_infra.initialize = AsyncMock(side_effect=Exception("DB connection failed"))

            lifespan = _make_standalone_lifespan()

            with pytest.raises(Exception, match="DB connection failed"):
                async with lifespan(app):
                    pass

            # app.state.redis should NOT be set to a closed connection
            # After the fix: app.state.redis should not be set at all
            # (or should be cleared on cleanup)
            assert (
                not hasattr(app.state, "redis") or app.state.redis is None
            ), "app.state.redis should not be set to a closed connection"
            assert (
                not hasattr(app.state, "db") or app.state.db is None
            ), "app.state.db should not be set when init fails"

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_initialize_db(self):
        """When Redis fails to connect, database should not be initialized."""
        from beadhub.api import _make_standalone_lifespan

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("Redis connection failed"))
        mock_redis.aclose = AsyncMock()

        class MockState:
            pass

        class MockApp:
            state = MockState()

        app = MockApp()

        async def mock_redis_from_url(*args, **kwargs):
            return mock_redis

        with (
            patch("beadhub.api.async_redis_from_url", side_effect=mock_redis_from_url),
            patch("beadhub.api.default_db_infra") as mock_db_infra,
            patch("beadhub.api.get_settings") as mock_settings,
            patch("beadhub.api.configure_logging"),
        ):
            mock_settings.return_value.redis_url = "redis://localhost:6379"
            mock_settings.return_value.log_level = "info"
            mock_db_infra.initialize = AsyncMock()

            lifespan = _make_standalone_lifespan()

            with pytest.raises(Exception, match="Redis connection failed"):
                async with lifespan(app):
                    pass

            # DB should not have been initialized
            mock_db_infra.initialize.assert_not_called()

            # Redis should still be cleaned up even though ping failed
            mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_initialization_sets_app_state(self):
        """When initialization succeeds, app.state should have both redis and db."""

        from beadhub.api import _make_standalone_lifespan

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()

        class MockState:
            pass

        class MockApp:
            state = MockState()

        app = MockApp()

        async def mock_redis_from_url(*args, **kwargs):
            return mock_redis

        with (
            patch("beadhub.api.async_redis_from_url", side_effect=mock_redis_from_url),
            patch("beadhub.api.default_db_infra") as mock_db_infra,
            patch("beadhub.api.get_settings") as mock_settings,
            patch("beadhub.api.configure_logging"),
        ):
            mock_settings.return_value.redis_url = "redis://localhost:6379"
            mock_settings.return_value.log_level = "info"
            mock_db_infra.initialize = AsyncMock()
            mock_db_infra.close = AsyncMock()

            lifespan = _make_standalone_lifespan()

            async with lifespan(app):
                # Inside the lifespan context, state should be set
                assert app.state.redis is mock_redis
                assert app.state.db is mock_db_infra

            # After exit, cleanup should have happened
            mock_redis.aclose.assert_called_once()
            mock_db_infra.close.assert_called_once()
