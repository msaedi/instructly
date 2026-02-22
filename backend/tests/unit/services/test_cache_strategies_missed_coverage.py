"""Tests targeting missed lines in app/services/cache_strategies.py.

Missed lines:
  119->128: warm_with_verification max retries with last_result
  141: warm_week delegates to warm_with_verification
  155: _write_week_cache_bundle when cache_service is None
  178: _week_cache_ttl_seconds when cache_service is None
  195->201: invalidate_and_warm when cache_service is None (no invalidation)
  233: ReadThroughCache _maybe_await with non-awaitable
  246->254: get_week_availability cache hit
  263->269: get_week_availability with force_refresh=True
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.services.cache_strategies import CacheWarmingStrategy, ReadThroughCache


class TestCacheWarmingStrategyMissedLines:
    """Test missed lines in CacheWarmingStrategy."""

    def test_write_week_cache_bundle_no_cache_service(self) -> None:
        """Line 155: _write_week_cache_bundle when cache_service is None => early return."""
        mock_db = MagicMock()
        strategy = CacheWarmingStrategy(cache_service=None, db=mock_db)

        import asyncio
        asyncio.run(strategy._write_week_cache_bundle(
            "instr1", date(2025, 1, 6), {"2025-01-06": []}, []
        ))
        # Should return without error

    def test_week_cache_ttl_no_cache_service(self) -> None:
        """Line 178: _week_cache_ttl_seconds when cache_service is None => RuntimeError."""
        mock_db = MagicMock()
        strategy = CacheWarmingStrategy(cache_service=None, db=mock_db)

        with pytest.raises(RuntimeError, match="Cache service required"):
            strategy._week_cache_ttl_seconds("instr1", date(2025, 1, 6))

    @pytest.mark.asyncio
    async def test_warm_with_verification_max_retries_reached(self) -> None:
        """Line 119->128: max retries reached, last_result is used."""
        mock_cache = MagicMock()
        mock_cache.key_builder = MagicMock()
        mock_cache.key_builder.build = MagicMock(return_value="test_key")
        mock_cache.TTL_TIERS = {"hot": 300, "warm": 600}
        mock_cache.set_json = MagicMock(return_value=None)  # sync return
        mock_db = MagicMock()

        strategy = CacheWarmingStrategy(cache_service=mock_cache, db=mock_db, max_retries=2)

        fake_data = {"2025-01-06": [{"start": "09:00", "end": "10:00"}]}

        with patch("app.services.availability_service.AvailabilityService") as MockAvail, \
             patch("app.services.cache_strategies.get_user_today_by_id", return_value=date(2025, 1, 6)):
            mock_service = MagicMock()
            mock_service.get_week_availability.return_value = fake_data
            MockAvail.return_value = mock_service

            # Expected 5 windows but we only have 1 => will fail verification
            result = await strategy.warm_with_verification(
                "instr1", date(2025, 1, 6), expected_window_count=5
            )

        assert result == fake_data

    @pytest.mark.asyncio
    async def test_warm_with_verification_no_cache_service(self) -> None:
        """Line 61-62: warm_with_verification when cache_service is None => return {}."""
        mock_db = MagicMock()
        strategy = CacheWarmingStrategy(cache_service=None, db=mock_db)

        result = await strategy.warm_with_verification("instr1", date(2025, 1, 6))
        assert result == {}

    @pytest.mark.asyncio
    async def test_warm_week_delegates(self) -> None:
        """Line 141: warm_week calls warm_with_verification."""
        mock_db = MagicMock()
        strategy = CacheWarmingStrategy(cache_service=None, db=mock_db)

        result = await strategy.warm_week("instr1", date(2025, 1, 6))
        assert result == {}

    @pytest.mark.asyncio
    async def test_invalidate_and_warm_no_cache_service(self) -> None:
        """Lines 195->201: invalidate_and_warm when cache_service is None."""
        mock_db = MagicMock()

        strategy = CacheWarmingStrategy(cache_service=None, db=mock_db)

        # When cache_service is None, warm_with_verification returns {} immediately.
        # No need to mock AvailabilityService since it won't be reached.
        await strategy.invalidate_and_warm(
            "instr1",
            [date(2025, 1, 6), date(2025, 1, 7)],
        )

    @pytest.mark.asyncio
    async def test_invalidate_and_warm_with_expected_changes(self) -> None:
        """Lines 195->201: invalidate_and_warm with expected_changes mapping."""
        mock_cache = MagicMock()
        mock_cache.invalidate_instructor_availability = MagicMock(return_value=None)
        mock_cache.key_builder = MagicMock()
        mock_cache.key_builder.build = MagicMock(return_value="test_key")
        mock_cache.TTL_TIERS = {"hot": 300, "warm": 600}
        mock_cache.set_json = MagicMock(return_value=None)
        mock_db = MagicMock()

        strategy = CacheWarmingStrategy(cache_service=mock_cache, db=mock_db, max_retries=1)

        fake_data = {"2025-01-06": []}

        with patch("app.services.availability_service.AvailabilityService") as MockAvail, \
             patch("app.services.cache_strategies.get_user_today_by_id", return_value=date(2025, 1, 6)):
            mock_service = MagicMock()
            mock_service.get_week_availability.return_value = fake_data
            MockAvail.return_value = mock_service

            await strategy.invalidate_and_warm(
                "instr1",
                [date(2025, 1, 6)],
                expected_changes={"2025-01-06": 0},
            )


class TestReadThroughCacheMissedLines:
    """Test missed lines in ReadThroughCache."""

    @pytest.mark.asyncio
    async def test_get_week_availability_cache_hit(self) -> None:
        """Line 246->254: cache hit returns cached data."""
        mock_cache = MagicMock()
        mock_cache.get = MagicMock(return_value={"2025-01-06": [{"start": "09:00"}]})
        mock_db = MagicMock()

        rtc = ReadThroughCache(cache_service=mock_cache, db=mock_db)
        result = await rtc.get_week_availability("instr1", date(2025, 1, 6))
        assert result == {"2025-01-06": [{"start": "09:00"}]}

    @pytest.mark.asyncio
    async def test_get_week_availability_force_refresh(self) -> None:
        """Line 263->269: force_refresh=True bypasses cache."""
        mock_cache = MagicMock()
        mock_cache.get = MagicMock(return_value={"old": "data"})
        mock_cache.cache_week_availability = MagicMock(return_value=None)
        mock_db = MagicMock()

        rtc = ReadThroughCache(cache_service=mock_cache, db=mock_db)

        with patch("app.services.availability_service.AvailabilityService") as MockAvail:
            mock_service = MagicMock()
            mock_service.get_week_availability.return_value = {"new": "data"}
            MockAvail.return_value = mock_service

            result = await rtc.get_week_availability(
                "instr1", date(2025, 1, 6), force_refresh=True
            )

        assert result == {"new": "data"}
        mock_cache.cache_week_availability.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_week_availability_no_cache_service(self) -> None:
        """Line 246: no cache_service => always fetch from DB."""
        mock_db = MagicMock()

        rtc = ReadThroughCache(cache_service=None, db=mock_db)

        with patch("app.services.availability_service.AvailabilityService") as MockAvail:
            mock_service = MagicMock()
            mock_service.get_week_availability.return_value = {"fresh": "data"}
            MockAvail.return_value = mock_service

            result = await rtc.get_week_availability("instr1", date(2025, 1, 6))

        assert result == {"fresh": "data"}

    @pytest.mark.asyncio
    async def test_maybe_await_non_awaitable(self) -> None:
        """Line 233: _maybe_await with a non-awaitable value."""
        mock_db = MagicMock()
        rtc = ReadThroughCache(cache_service=None, db=mock_db)
        result = await rtc._maybe_await("plain_value")
        assert result == "plain_value"

    @pytest.mark.asyncio
    async def test_maybe_await_awaitable(self) -> None:
        """_maybe_await with an awaitable value."""
        mock_db = MagicMock()
        rtc = ReadThroughCache(cache_service=None, db=mock_db)

        async def _coro():
            return "awaited_value"

        result = await rtc._maybe_await(_coro())
        assert result == "awaited_value"
