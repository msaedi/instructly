"""Unit coverage for app.core.booking_lock – uncovered L38,124-129."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import app.core.booking_lock as lock_mod


class TestGetSyncRedis:
    """L38: double-check locking and ping failure path."""

    def test_returns_cached_client(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            mock_client = MagicMock()
            lock_mod._SYNC_REDIS = mock_client
            result = lock_mod._get_sync_redis()
            assert result is mock_client
        finally:
            lock_mod._SYNC_REDIS = original

    def test_creates_client_when_none(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            lock_mod._SYNC_REDIS = None
            mock_client = MagicMock()
            mock_client.ping.return_value = True

            with patch("app.core.booking_lock.Redis") as MockRedis:
                MockRedis.from_url.return_value = mock_client
                result = lock_mod._get_sync_redis()
                assert result is mock_client
        finally:
            lock_mod._SYNC_REDIS = original

    def test_returns_none_on_ping_failure(self) -> None:
        """L38: When Redis.from_url or ping raises, returns None."""
        original = lock_mod._SYNC_REDIS
        try:
            lock_mod._SYNC_REDIS = None

            with patch("app.core.booking_lock.Redis") as MockRedis:
                MockRedis.from_url.side_effect = ConnectionError("refused")
                result = lock_mod._get_sync_redis()
                assert result is None
        finally:
            lock_mod._SYNC_REDIS = original


class TestAcquireBookingLock:
    """L124-129: async acquire failure -> fail-open (returns True)."""

    @pytest.mark.asyncio
    async def test_acquire_fail_open(self) -> None:
        """When async lock acquisition fails, booking_lock returns True (fail-open)."""
        with patch("app.core.booking_lock._acquire_async_lock", side_effect=RuntimeError("redis down")):
            with patch("app.core.booking_lock.prometheus_metrics"):
                result = await lock_mod.acquire_booking_lock("booking-01")
                assert result is True

    @pytest.mark.asyncio
    async def test_acquire_success(self) -> None:
        with patch("app.core.booking_lock._acquire_async_lock", return_value=True):
            with patch("app.core.booking_lock.prometheus_metrics"):
                result = await lock_mod.acquire_booking_lock("booking-01")
                assert result is True

    @pytest.mark.asyncio
    async def test_acquire_blocked(self) -> None:
        with patch("app.core.booking_lock._acquire_async_lock", return_value=False):
            with patch("app.core.booking_lock.prometheus_metrics"):
                result = await lock_mod.acquire_booking_lock("booking-01")
                assert result is False


class TestReleaseBookingLock:
    """Release path coverage."""

    @pytest.mark.asyncio
    async def test_release_success(self) -> None:
        with patch("app.core.booking_lock._release_async_lock") as mock_release:
            with patch("app.core.booking_lock.prometheus_metrics"):
                await lock_mod.release_booking_lock("booking-01")
                mock_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_error_logged(self) -> None:
        with patch(
            "app.core.booking_lock._release_async_lock",
            side_effect=RuntimeError("gone"),
        ):
            with patch("app.core.booking_lock.prometheus_metrics"):
                # Should not raise
                await lock_mod.release_booking_lock("booking-01")


class TestSyncLock:
    """Sync lock acquire/release."""

    def test_sync_acquire_redis_unavailable(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            lock_mod._SYNC_REDIS = None
            with patch("app.core.booking_lock.Redis") as MockRedis:
                MockRedis.from_url.side_effect = ConnectionError("no redis")
                with patch("app.core.booking_lock.prometheus_metrics"):
                    result = lock_mod.acquire_booking_lock_sync("booking-01")
                    assert result is True  # fail-open
        finally:
            lock_mod._SYNC_REDIS = original

    def test_sync_acquire_set_error(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            mock_client = MagicMock()
            mock_client.set.side_effect = RuntimeError("set failed")
            lock_mod._SYNC_REDIS = mock_client
            with patch("app.core.booking_lock.prometheus_metrics"):
                result = lock_mod.acquire_booking_lock_sync("booking-01")
                assert result is True  # fail-open
        finally:
            lock_mod._SYNC_REDIS = original

    def test_sync_release_redis_unavailable(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            lock_mod._SYNC_REDIS = None
            with patch("app.core.booking_lock.Redis") as MockRedis:
                MockRedis.from_url.side_effect = ConnectionError("no redis")
                with patch("app.core.booking_lock.prometheus_metrics"):
                    lock_mod.release_booking_lock_sync("booking-01")
        finally:
            lock_mod._SYNC_REDIS = original

    def test_sync_release_success(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            mock_client = MagicMock()
            mock_client.delete.return_value = 1
            lock_mod._SYNC_REDIS = mock_client
            with patch("app.core.booking_lock.prometheus_metrics"):
                lock_mod.release_booking_lock_sync("booking-01")
                mock_client.delete.assert_called_once()
        finally:
            lock_mod._SYNC_REDIS = original

    def test_sync_release_not_found(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            mock_client = MagicMock()
            mock_client.delete.return_value = 0
            lock_mod._SYNC_REDIS = mock_client
            with patch("app.core.booking_lock.prometheus_metrics"):
                lock_mod.release_booking_lock_sync("booking-01")
        finally:
            lock_mod._SYNC_REDIS = original

    def test_sync_release_error(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            mock_client = MagicMock()
            mock_client.delete.side_effect = RuntimeError("delete failed")
            lock_mod._SYNC_REDIS = mock_client
            with patch("app.core.booking_lock.prometheus_metrics"):
                lock_mod.release_booking_lock_sync("booking-01")
        finally:
            lock_mod._SYNC_REDIS = original


class TestContextManagers:
    """Context manager paths."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        with patch("app.core.booking_lock._acquire_async_lock", return_value=True):
            with patch("app.core.booking_lock._release_async_lock") as mock_release:
                with patch("app.core.booking_lock.prometheus_metrics"):
                    async with lock_mod.booking_lock("booking-01") as acquired:
                        assert acquired is True
                    mock_release.assert_called_once()

    def test_sync_context_manager(self) -> None:
        original = lock_mod._SYNC_REDIS
        try:
            mock_client = MagicMock()
            mock_client.set.return_value = True
            mock_client.delete.return_value = 1
            lock_mod._SYNC_REDIS = mock_client
            with patch("app.core.booking_lock.prometheus_metrics"):
                with lock_mod.booking_lock_sync("booking-01") as acquired:
                    assert acquired is True
                mock_client.delete.assert_called_once()
        finally:
            lock_mod._SYNC_REDIS = original
