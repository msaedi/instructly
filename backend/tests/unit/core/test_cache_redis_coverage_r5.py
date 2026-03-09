# backend/tests/unit/core/test_cache_redis_coverage_r5.py
"""
Round 5 Coverage Tests for cache_redis module.

Target: Raise coverage from 77.63% to 92%+
Missed lines: 51->54, 61->65, 69, 85-93, 102
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core import cache_redis
from app.core.config import settings


class TestGetAsyncCacheRedisClientCoverage:
    """Coverage tests for get_async_cache_redis_client function."""

    @staticmethod
    def _cleanup_loop_state(loop):
        """Clean up cache_redis state for a given loop."""
        if loop in cache_redis._clients_by_loop:
            del cache_redis._clients_by_loop[loop]
        if loop in cache_redis._locks_by_loop:
            del cache_redis._locks_by_loop[loop]

    @pytest.mark.asyncio
    async def test_testing_mode_closes_existing_client(self, monkeypatch) -> None:
        """Lines 51->54: In test mode, closes existing client and returns None."""
        loop = asyncio.get_running_loop()
        dummy = AsyncMock()
        dummy.connection_pool = SimpleNamespace(disconnect=AsyncMock())
        cache_redis._clients_by_loop[loop] = dummy

        monkeypatch.setattr(settings, "is_testing", True, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)

        result = await cache_redis.get_async_cache_redis_client()

        assert result is None
        dummy.aclose.assert_awaited_once_with(close_connection_pool=False)
        assert loop not in cache_redis._clients_by_loop

    @pytest.mark.asyncio
    async def test_testing_mode_handles_close_exception(self, monkeypatch) -> None:
        """Lines 52-53: Suppresses exceptions when closing existing client."""
        loop = asyncio.get_running_loop()
        dummy = AsyncMock()
        dummy.aclose.side_effect = Exception("Close failed")
        dummy.connection_pool = SimpleNamespace(disconnect=AsyncMock())
        cache_redis._clients_by_loop[loop] = dummy

        monkeypatch.setattr(settings, "is_testing", True, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)

        # Should not raise despite close error
        result = await cache_redis.get_async_cache_redis_client()

        assert result is None

    @pytest.mark.asyncio
    async def test_testing_mode_without_cached_client_short_circuits_cleanly(self, monkeypatch) -> None:
        loop = asyncio.get_running_loop()
        self._cleanup_loop_state(loop)

        monkeypatch.setattr(settings, "is_testing", True, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)

        with patch.object(cache_redis, "_close_cache_client", AsyncMock()) as close_mock:
            with patch.object(cache_redis.AsyncRedis, "from_url") as from_url_mock:
                result = await cache_redis.get_async_cache_redis_client()

        assert result is None
        close_mock.assert_not_awaited()
        from_url_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_creation_branch(self, monkeypatch) -> None:
        """Lines 61->65: Creates lock when not present for loop."""
        loop = asyncio.get_running_loop()

        # Ensure no lock exists
        self._cleanup_loop_state(loop)

        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

        # Mock the AsyncRedis to fail ping (so we don't actually connect)
        dummy_client = AsyncMock()
        dummy_client.ping.side_effect = RuntimeError("Connection failed")
        dummy_client.connection_pool = SimpleNamespace(disconnect=AsyncMock())

        try:
            with patch.object(cache_redis.AsyncRedis, "from_url", return_value=dummy_client):
                result = await cache_redis.get_async_cache_redis_client()

            assert result is None
            # Lock should have been created
            assert loop in cache_redis._locks_by_loop
        finally:
            self._cleanup_loop_state(loop)

    @pytest.mark.asyncio
    async def test_reuses_existing_client_after_lock(self, monkeypatch) -> None:
        """Line 69: Returns existing client found after acquiring lock."""
        loop = asyncio.get_running_loop()
        dummy = AsyncMock()

        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

        try:
            # Pre-set the client
            cache_redis._clients_by_loop[loop] = dummy

            result = await cache_redis.get_async_cache_redis_client()

            # Should return existing client
            assert result is dummy
        finally:
            self._cleanup_loop_state(loop)

    @pytest.mark.asyncio
    async def test_successful_connection_stores_client(self, monkeypatch) -> None:
        """Lines 85-87: Stores and returns client on successful connection."""
        loop = asyncio.get_running_loop()

        # Clean state
        self._cleanup_loop_state(loop)

        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

        dummy_client = AsyncMock()
        dummy_client.ping.return_value = True

        try:
            with patch.object(cache_redis.AsyncRedis, "from_url", return_value=dummy_client):
                result = await cache_redis.get_async_cache_redis_client()

            assert result is dummy_client
            assert loop in cache_redis._clients_by_loop
            assert cache_redis._clients_by_loop[loop] is dummy_client
        finally:
            self._cleanup_loop_state(loop)

    @pytest.mark.asyncio
    async def test_event_loop_closed_error(self, monkeypatch) -> None:
        """Lines 88-90: Handles 'Event loop is closed' RuntimeError."""
        loop = asyncio.get_running_loop()

        # Clean state
        self._cleanup_loop_state(loop)

        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

        # Create a mock lock that raises "Event loop is closed" when acquired
        mock_lock = AsyncMock()
        mock_lock.__aenter__ = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
        mock_lock.__aexit__ = AsyncMock()

        try:
            # Pre-set the lock
            cache_redis._locks_by_loop[loop] = mock_lock

            result = await cache_redis.get_async_cache_redis_client()

            assert result is None
        finally:
            self._cleanup_loop_state(loop)

    @pytest.mark.asyncio
    async def test_generic_exception_returns_none(self, monkeypatch) -> None:
        """Lines 92-93: Generic exceptions return None."""
        loop = asyncio.get_running_loop()

        # Clean state
        self._cleanup_loop_state(loop)

        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

        try:
            # Make from_url raise a generic exception
            with patch.object(
                cache_redis.AsyncRedis, "from_url",
                side_effect=Exception("Generic error")
            ):
                result = await cache_redis.get_async_cache_redis_client()

            assert result is None
        finally:
            self._cleanup_loop_state(loop)

    @pytest.mark.asyncio
    async def test_runtime_error_not_event_loop_closed_reraises(self, monkeypatch) -> None:
        """Lines 88-91: Re-raises RuntimeError that's not 'Event loop is closed'."""
        loop = asyncio.get_running_loop()

        # Clean state
        self._cleanup_loop_state(loop)

        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

        # Create a mock lock that raises a different RuntimeError
        mock_lock = AsyncMock()
        mock_lock.__aenter__ = AsyncMock(side_effect=RuntimeError("Something else went wrong"))
        mock_lock.__aexit__ = AsyncMock()

        try:
            cache_redis._locks_by_loop[loop] = mock_lock

            with pytest.raises(RuntimeError, match="Something else went wrong"):
                await cache_redis.get_async_cache_redis_client()
        finally:
            self._cleanup_loop_state(loop)


class TestCloseAsyncCacheRedisClient:
    """Coverage tests for close_async_cache_redis_client function."""

    @pytest.mark.asyncio
    async def test_close_when_no_client_exists(self) -> None:
        """Line 102: Returns early when no client exists."""
        loop = asyncio.get_running_loop()

        # Ensure no client
        if loop in cache_redis._clients_by_loop:
            del cache_redis._clients_by_loop[loop]

        # Should not raise
        await cache_redis.close_async_cache_redis_client()

    @pytest.mark.asyncio
    async def test_close_disconnects_connection_pool(self) -> None:
        """Lines 106-107: Disconnects connection pool on close."""
        loop = asyncio.get_running_loop()

        dummy = AsyncMock()
        dummy.connection_pool = SimpleNamespace(disconnect=AsyncMock())
        cache_redis._clients_by_loop[loop] = dummy

        await cache_redis.close_async_cache_redis_client()

        dummy.aclose.assert_awaited_once_with(close_connection_pool=False)
        dummy.connection_pool.disconnect.assert_awaited()
        assert loop not in cache_redis._clients_by_loop

    @pytest.mark.asyncio
    async def test_close_handles_disconnect_exception(self) -> None:
        """Line 106: Handles exceptions when disconnecting pool."""
        loop = asyncio.get_running_loop()

        dummy = AsyncMock()
        mock_disconnect = AsyncMock(side_effect=Exception("Disconnect failed"))
        dummy.connection_pool = SimpleNamespace(disconnect=mock_disconnect)
        cache_redis._clients_by_loop[loop] = dummy

        # Should not raise despite disconnect error
        await cache_redis.close_async_cache_redis_client()

        dummy.aclose.assert_awaited_once_with(close_connection_pool=False)


@pytest.mark.asyncio
async def test_disconnect_pool_connections_deduplicates_shared_connection() -> None:
    shared = SimpleNamespace(disconnect=AsyncMock())
    pool = SimpleNamespace(
        _available_connections=[shared],
        _in_use_connections=[shared],
    )

    await cache_redis._disconnect_pool_connections(pool)

    shared.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_pool_connections_reraises_first_error_after_attempting_all() -> None:
    first = RuntimeError("first disconnect failed")
    conn_one = SimpleNamespace(disconnect=AsyncMock(side_effect=first))
    conn_two = SimpleNamespace(disconnect=AsyncMock())
    pool = SimpleNamespace(
        _available_connections=[conn_one],
        _in_use_connections=[conn_two],
    )

    with pytest.raises(RuntimeError, match="first disconnect failed"):
        await cache_redis._disconnect_pool_connections(pool)

    conn_one.disconnect.assert_awaited_once()
    conn_two.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_pool_connections_ignores_missing_disconnect_hook() -> None:
    pool = SimpleNamespace(
        _available_connections=None,
        _in_use_connections=None,
        disconnect=None,
    )

    await cache_redis._disconnect_pool_connections(pool)


@pytest.mark.asyncio
async def test_disconnect_pool_connections_uses_pool_disconnect_when_lists_absent() -> None:
    disconnect = AsyncMock()
    pool = SimpleNamespace(
        _available_connections=None,
        _in_use_connections=None,
        disconnect=disconnect,
    )

    await cache_redis._disconnect_pool_connections(pool)

    disconnect.assert_awaited_once()
