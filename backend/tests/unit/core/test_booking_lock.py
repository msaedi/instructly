"""
Unit tests for booking_lock.py.

Coverage:
1) Key generation
2) Lock acquisition/release
3) TTL propagation
4) Graceful degradation when Redis is unavailable
5) Async/sync context manager behavior
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.core.booking_lock import (
    _lock_key,
    _namespaced_key,
    acquire_booking_lock,
    acquire_booking_lock_sync,
    booking_lock,
    booking_lock_sync,
    release_booking_lock,
    release_booking_lock_sync,
)


class TestKeyGeneration:
    def test_lock_key_format(self):
        assert _lock_key("ABC123") == "booking:ABC123:mutex"
        assert _lock_key("01KDGCP1R4N6AQKXNWV4PFY2HB") == "booking:01KDGCP1R4N6AQKXNWV4PFY2HB:mutex"

    def test_namespaced_key_format(self):
        namespaced = _namespaced_key("booking:ABC123:mutex")
        assert namespaced.endswith(":lock:booking:ABC123:mutex")
        assert ":lock:" in namespaced

    def test_async_and_sync_use_same_key_format(self):
        booking_id = "TEST123"
        base_key = _lock_key(booking_id)
        assert base_key == "booking:TEST123:mutex"
        namespaced = _namespaced_key(base_key)
        assert namespaced.endswith(":lock:booking:TEST123:mutex")


class TestLockAcquisition:
    @pytest.mark.asyncio
    async def test_acquire_lock_success(self):
        with patch(
            "app.core.booking_lock._acquire_async_lock", new_callable=AsyncMock
        ) as mock_acquire:
            mock_acquire.return_value = True
            result = await acquire_booking_lock("ABC123")
        assert result is True
        mock_acquire.assert_awaited_once_with("booking:ABC123:mutex", ttl_s=90)

    @pytest.mark.asyncio
    async def test_acquire_lock_already_held(self):
        with patch(
            "app.core.booking_lock._acquire_async_lock", new_callable=AsyncMock
        ) as mock_acquire:
            mock_acquire.return_value = False
            result = await acquire_booking_lock("ABC123")
        assert result is False
        mock_acquire.assert_awaited_once_with("booking:ABC123:mutex", ttl_s=90)

    @pytest.mark.asyncio
    async def test_acquire_lock_passes_ttl(self):
        with patch(
            "app.core.booking_lock._acquire_async_lock", new_callable=AsyncMock
        ) as mock_acquire:
            await acquire_booking_lock("ABC123", ttl_s=45)
        mock_acquire.assert_awaited_once_with("booking:ABC123:mutex", ttl_s=45)

    def test_sync_acquire_lock_success(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        with patch("app.core.booking_lock._get_sync_redis", return_value=mock_redis):
            result = acquire_booking_lock_sync("ABC123")
        assert result is True
        mock_redis.set.assert_called_once_with(
            _namespaced_key("booking:ABC123:mutex"), ANY, nx=True, ex=90
        )

    def test_sync_acquire_lock_already_held(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = False
        with patch("app.core.booking_lock._get_sync_redis", return_value=mock_redis):
            result = acquire_booking_lock_sync("ABC123", ttl_s=120)
        assert result is False
        mock_redis.set.assert_called_once_with(
            _namespaced_key("booking:ABC123:mutex"), ANY, nx=True, ex=120
        )


class TestLockRelease:
    @pytest.mark.asyncio
    async def test_release_lock_calls_release(self):
        with patch(
            "app.core.booking_lock._release_async_lock", new_callable=AsyncMock
        ) as mock_release:
            await release_booking_lock("ABC123")
        mock_release.assert_awaited_once_with("booking:ABC123:mutex")

    @pytest.mark.asyncio
    async def test_lock_released_on_exception(self):
        with patch(
            "app.core.booking_lock._acquire_async_lock", new_callable=AsyncMock
        ) as mock_acquire, patch(
            "app.core.booking_lock._release_async_lock", new_callable=AsyncMock
        ) as mock_release:
            mock_acquire.return_value = True
            with pytest.raises(ValueError):
                async with booking_lock("ABC123") as acquired:
                    assert acquired is True
                    raise ValueError("boom")
        mock_release.assert_awaited_once_with("booking:ABC123:mutex")

    def test_sync_lock_released_on_exception(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        with patch("app.core.booking_lock._get_sync_redis", return_value=mock_redis):
            with pytest.raises(ValueError):
                with booking_lock_sync("ABC123") as acquired:
                    assert acquired is True
                    raise ValueError("boom")
        mock_redis.delete.assert_called_once_with(_namespaced_key("booking:ABC123:mutex"))

    def test_release_lock_sync_calls_delete(self):
        mock_redis = MagicMock()
        with patch("app.core.booking_lock._get_sync_redis", return_value=mock_redis):
            release_booking_lock_sync("ABC123")
        mock_redis.delete.assert_called_once_with(_namespaced_key("booking:ABC123:mutex"))


class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_redis_unavailable_returns_true_async(self):
        with patch(
            "app.ratelimit.locks.get_redis", new=AsyncMock(side_effect=Exception("down"))
        ):
            result = await acquire_booking_lock("ABC123")
        assert result is True

    def test_sync_redis_unavailable_returns_true(self):
        with patch("app.core.booking_lock._get_sync_redis", return_value=None):
            result = acquire_booking_lock_sync("ABC123")
        assert result is True


class TestContextManagers:
    @pytest.mark.asyncio
    async def test_async_context_yields_acquisition_status(self):
        with patch(
            "app.core.booking_lock._acquire_async_lock", new_callable=AsyncMock
        ) as mock_acquire, patch(
            "app.core.booking_lock._release_async_lock", new_callable=AsyncMock
        ) as mock_release:
            mock_acquire.return_value = True
            async with booking_lock("ABC123") as acquired:
                assert acquired is True
        mock_release.assert_awaited_once_with("booking:ABC123:mutex")

    @pytest.mark.asyncio
    async def test_async_context_yields_false_when_held(self):
        with patch(
            "app.core.booking_lock._acquire_async_lock", new_callable=AsyncMock
        ) as mock_acquire, patch(
            "app.core.booking_lock._release_async_lock", new_callable=AsyncMock
        ) as mock_release:
            mock_acquire.return_value = False
            async with booking_lock("ABC123") as acquired:
                assert acquired is False
        mock_release.assert_not_called()

    def test_sync_context_yields_acquisition_status(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        with patch("app.core.booking_lock._get_sync_redis", return_value=mock_redis):
            with booking_lock_sync("ABC123") as acquired:
                assert acquired is True
        mock_redis.delete.assert_called_once_with(_namespaced_key("booking:ABC123:mutex"))

    def test_sync_context_no_release_if_not_acquired(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = False
        with patch("app.core.booking_lock._get_sync_redis", return_value=mock_redis):
            with booking_lock_sync("ABC123") as acquired:
                assert acquired is False
        mock_redis.delete.assert_not_called()
