# backend/tests/unit/services/messaging/test_redis_pubsub.py
"""Unit tests for Redis Pub/Sub manager."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.messaging.redis_pubsub import RedisPubSubManager


@pytest.fixture
def pubsub_manager() -> RedisPubSubManager:
    """Create a fresh manager instance for testing."""
    # Reset singleton for testing
    RedisPubSubManager._instance = None
    return RedisPubSubManager()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create mock async Redis client."""
    mock = AsyncMock()
    mock.publish = AsyncMock(return_value=1)
    return mock


class TestRedisPubSubManagerInitialization:
    """Tests for manager initialization."""

    def test_singleton_pattern(self) -> None:
        """Verify manager is a singleton."""
        RedisPubSubManager._instance = None
        manager1 = RedisPubSubManager()
        manager2 = RedisPubSubManager()

        assert manager1 is manager2

    def test_is_initialized_before_init(self, pubsub_manager: RedisPubSubManager) -> None:
        """Verify is_initialized is False before initialization."""
        assert pubsub_manager.is_initialized is False

    @pytest.mark.asyncio
    async def test_is_initialized_after_init(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify is_initialized is True after initialization."""
        await pubsub_manager.initialize(mock_redis)

        assert pubsub_manager.is_initialized is True


class TestPublishToUser:
    """Tests for publish_to_user method."""

    @pytest.mark.asyncio
    async def test_publish_to_user_success(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify successful publish returns subscriber count."""
        await pubsub_manager.initialize(mock_redis)

        event = {"type": "test", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {}}
        result = await pubsub_manager.publish_to_user("01USER", event)

        assert result == 1
        mock_redis.publish.assert_called_once()

        # Verify channel name
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "user:01USER"

    @pytest.mark.asyncio
    async def test_publish_to_user_correct_payload(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify event is serialized correctly."""
        await pubsub_manager.initialize(mock_redis)

        event = {"type": "new_message", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {"key": "value"}}
        await pubsub_manager.publish_to_user("01USER", event)

        # Verify payload is JSON serialized
        call_args = mock_redis.publish.call_args
        payload = call_args[0][1]
        parsed = json.loads(payload)
        assert parsed == event

    @pytest.mark.asyncio
    async def test_publish_continues_on_redis_failure(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify fire-and-forget: Redis failure doesn't raise."""
        mock_redis.publish = AsyncMock(side_effect=Exception("Redis down"))
        await pubsub_manager.initialize(mock_redis)

        event = {"type": "test", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {}}
        result = await pubsub_manager.publish_to_user("01USER", event)

        # Should return 0, not raise
        assert result == 0
        assert pubsub_manager.get_stats()["error_count"] == 1

    @pytest.mark.asyncio
    async def test_publish_without_init_returns_zero(
        self, pubsub_manager: RedisPubSubManager
    ) -> None:
        """Verify publishing before init returns 0."""
        event = {"type": "test", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {}}
        result = await pubsub_manager.publish_to_user("01USER", event)

        assert result == 0

    @pytest.mark.asyncio
    async def test_publish_increments_publish_count(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify publish count is incremented on success."""
        await pubsub_manager.initialize(mock_redis)

        initial_count = pubsub_manager.get_stats()["publish_count"]

        event = {"type": "test", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {}}
        await pubsub_manager.publish_to_user("01USER", event)

        assert pubsub_manager.get_stats()["publish_count"] == initial_count + 1


class TestPublishToUsers:
    """Tests for publish_to_users method."""

    @pytest.mark.asyncio
    async def test_publish_to_multiple_users(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify publishing to multiple users."""
        await pubsub_manager.initialize(mock_redis)

        event = {"type": "new_message", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {}}
        result = await pubsub_manager.publish_to_users(["01USER1", "01USER2", "01USER3"], event)

        assert result == {"01USER1": 1, "01USER2": 1, "01USER3": 1}
        assert mock_redis.publish.call_count == 3

    @pytest.mark.asyncio
    async def test_publish_to_users_empty_list(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify publishing to empty user list."""
        await pubsub_manager.initialize(mock_redis)

        event = {"type": "new_message", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {}}
        result = await pubsub_manager.publish_to_users([], event)

        assert result == {}
        mock_redis.publish.assert_not_called()


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats_initial(self, pubsub_manager: RedisPubSubManager) -> None:
        """Verify initial stats."""
        stats = pubsub_manager.get_stats()

        assert stats["initialized"] is False
        assert stats["publish_count"] == 0
        assert stats["error_count"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_after_operations(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        """Verify stats after operations."""
        await pubsub_manager.initialize(mock_redis)

        event = {"type": "test", "schema_version": 1, "timestamp": "2024-01-01T00:00:00Z", "payload": {}}

        # Successful publish
        await pubsub_manager.publish_to_user("01USER1", event)

        # Failed publish
        mock_redis.publish = AsyncMock(side_effect=Exception("Redis down"))
        await pubsub_manager.publish_to_user("01USER2", event)

        stats = pubsub_manager.get_stats()
        assert stats["initialized"] is True
        assert stats["publish_count"] == 1
        assert stats["error_count"] == 1


class TestSubscribe:
    """Tests for deprecated subscribe behavior."""

    @pytest.mark.asyncio
    async def test_subscribe_requires_initialization(
        self, pubsub_manager: RedisPubSubManager
    ) -> None:
        with pytest.warns(DeprecationWarning):
            with pytest.raises(RuntimeError):
                async with pubsub_manager.subscribe("01USER"):
                    pass

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribes_on_exit(
        self, pubsub_manager: RedisPubSubManager, mock_redis: AsyncMock
    ) -> None:
        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        pubsub.unsubscribe = AsyncMock()
        pubsub.aclose = AsyncMock()
        mock_redis.pubsub = Mock(return_value=pubsub)
        await pubsub_manager.initialize(mock_redis)

        with pytest.warns(DeprecationWarning):
            async with pubsub_manager.subscribe("01USER") as subscriber:
                assert subscriber is pubsub

        pubsub.subscribe.assert_awaited_once_with("user:01USER")
        pubsub.unsubscribe.assert_awaited_once_with("user:01USER")
        pubsub.aclose.assert_awaited_once()
