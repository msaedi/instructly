# backend/tests/services/test_cache_clean_architecture.py
"""
Test that the cache system uses clean architecture with business concept
keys and no references to removed concepts.

FIXED VERSION - Addresses test failures:
1. Fixed cache prefix expectations
2. Fixed patch paths for imports
3. Removed incompatible Redis parameters

Run with:
    cd backend
    pytest tests/services/test_cache_clean_architecture.py -v
"""

from datetime import date, time
from unittest.mock import Mock, patch

import pytest

from app.services.cache_service import CacheKeyBuilder, CacheService


class TestCacheKeyPatterns:
    """Test cache keys use clean business concepts."""

    def test_cache_key_builder_uses_clean_prefixes(self):
        """Test CacheKeyBuilder uses business concept prefixes."""
        CacheKeyBuilder()

        # Test all defined prefixes - none should reference slots
        for prefix in CacheKeyBuilder.PREFIXES.values():
            assert "slot_id" not in prefix
            assert "availability_id" not in prefix  # Could be InstructorAvailability ID

        # Prefixes should be business concepts
        assert CacheKeyBuilder.PREFIXES["availability"] == "avail"
        assert CacheKeyBuilder.PREFIXES["booking"] == "book"
        assert CacheKeyBuilder.PREFIXES["instructor"] == "inst"

    def test_cache_key_generation_is_clean(self):
        """Test generated cache keys don't contain removed concepts."""
        builder = CacheKeyBuilder()

        # Test various key patterns
        test_keys = [
            builder.build("availability", "week", 123, date(2025, 7, 15)),
            builder.build("booking", 456, date(2025, 7, 15)),
            builder.build("instructor", "profile", 789),
            builder.build("conflict", 123, date(2025, 7, 15), "hash123"),
        ]

        for key in test_keys:
            # Keys should not contain removed concepts
            assert "slot_id" not in key
            assert "availability_slot_id" not in key
            assert "is_available" not in key

            # Keys should be well-formed
            assert ":" in key  # Proper separator
            assert key[0] != ":"  # No leading separator
            assert key[-1] != ":"  # No trailing separator

    def test_week_availability_key_format(self):
        """Test week availability cache key uses instructor and date."""
        builder = CacheKeyBuilder()

        instructor_id = 123
        week_start = date(2025, 7, 14)  # Monday

        key = builder.build("availability", "week", instructor_id, week_start)

        # Should be formatted as expected
        assert key == "avail:week:123:2025-07-14"

        # Should NOT contain slot references
        assert "slot" not in key

    def test_complex_key_hashing_is_clean(self):
        """Test complex key hashing doesn't include removed fields."""
        builder = CacheKeyBuilder()

        # Test data that might be hashed
        clean_data = {
            "instructor_id": 123,
            "date": "2025-07-15",
            "start_time": "09:00",
            "end_time": "10:00",
        }

        # Generate hash
        hash_key = builder.hash_complex_key(clean_data)

        # Hash should be short and clean
        assert len(hash_key) == 12
        assert hash_key.isalnum()  # Only alphanumeric

        # Adding removed fields should generate different hash
        dirty_data = clean_data.copy()
        dirty_data["availability_slot_id"] = 999

        dirty_hash = builder.hash_complex_key(dirty_data)
        assert hash_key != dirty_hash  # Different data = different hash


class TestCacheDataStructures:
    """Test that cached data doesn't contain removed fields."""

    @pytest.fixture
    def cache_service(self, db):
        """Create cache service with mocked Redis."""
        # Mock Redis client
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.ping.return_value = True

        return CacheService(db, redis_client=mock_redis)

    def test_cache_week_availability_uses_clean_data(self, cache_service):
        """Test caching week availability doesn't store removed fields."""
        instructor_id = 123
        week_start = date(2025, 7, 14)

        # Clean availability data (what we should cache)
        availability_data = {
            "2025-07-14": [
                {
                    "id": 1,
                    "instructor_id": instructor_id,
                    "date": "2025-07-14",
                    "start_time": "09:00",
                    "end_time": "12:00",
                }
            ],
            "2025-07-15": [
                {
                    "id": 2,
                    "instructor_id": instructor_id,
                    "date": "2025-07-15",
                    "start_time": "14:00",
                    "end_time": "17:00",
                }
            ],
        }

        # Cache the data
        result = cache_service.cache_week_availability(instructor_id, week_start, availability_data)
        assert result is True

        # Verify what was cached
        cache_service.redis.setex.assert_called_once()
        call_args = cache_service.redis.setex.call_args

        # Check the key
        cached_key = call_args[0][0]
        assert "week" in cached_key
        assert str(instructor_id) in cached_key
        assert "slot_id" not in cached_key

        # Check the TTL (should be hot tier for current/future weeks)
        ttl = call_args[0][1]
        assert ttl == CacheService.TTL_TIERS["hot"]  # 5 minutes

    def test_cache_booking_conflicts_uses_clean_data(self, cache_service):
        """Test caching booking conflicts uses time-based data."""
        instructor_id = 123
        check_date = date(2025, 7, 15)
        start_time = time(9, 0)
        end_time = time(10, 0)

        # Conflict data (should not have slot references)
        conflicts = [
            {
                "booking_id": 456,
                "start_time": "09:30",
                "end_time": "10:30",
                "student_name": "John Doe",
            }
        ]

        # Cache the conflicts
        result = cache_service.cache_booking_conflicts(instructor_id, check_date, start_time, end_time, conflicts)
        assert result is True

        # Verify the cache operation
        cache_service.redis.setex.assert_called_once()
        call_args = cache_service.redis.setex.call_args

        # Key should include instructor and date, but not slots
        cached_key = call_args[0][0]
        # FIXED: Changed from "conf" to "con" to match actual prefix
        assert "con" in cached_key  # Conflict prefix (not "conf")
        assert str(instructor_id) in cached_key
        assert "slot" not in cached_key

    def test_cache_invalidation_patterns_are_clean(self, cache_service):
        """Test cache invalidation uses clean patterns."""
        # Mock scan_iter for pattern deletion
        cache_service.redis.scan_iter.return_value = [
            "avail:week:123:2025-07-14",
            "con:123:2025-07-15:abc123",  # FIXED: Using "con" not "conf"
        ]

        instructor_id = 123
        dates = [date(2025, 7, 14), date(2025, 7, 15)]

        # Invalidate caches
        cache_service.invalidate_instructor_availability(instructor_id, dates)

        # Check the patterns used for invalidation
        scan_calls = cache_service.redis.scan_iter.call_args_list

        for call in scan_calls:
            pattern = call[1]["match"]
            # Patterns should use instructor ID
            assert "123" in pattern
            # Should NOT look for slot patterns
            assert "slot_id" not in pattern
            assert "availability_slot" not in pattern

    def test_cache_decorator_uses_clean_keys(self, cache_service):
        """Test the @cached decorator generates clean keys."""

        # Example function with cache decorator
        @cache_service.cached(
            key_func=lambda self, instructor_id, date: f"test:data:{instructor_id}:{date}",
            tier="warm",
        )
        def get_test_data(self, instructor_id: int, date: date):
            return {"instructor_id": instructor_id, "date": str(date), "data": "test"}

        # Call the function
        get_test_data(None, 123, date(2025, 7, 15))

        # Verify cache was checked/set
        cache_service.redis.get.assert_called_once()
        cache_service.redis.setex.assert_called_once()

        # Check the key used
        get_key = cache_service.redis.get.call_args[0][0]
        assert get_key == "test:data:123:2025-07-15"
        assert "slot" not in get_key


class TestCacheWarmingStrategies:
    """Test cache warming uses clean architecture."""

    @pytest.mark.asyncio
    async def test_cache_warming_uses_service_layer(self, db):
        """Test cache warming delegates to service layer, not direct queries."""
        from app.services.cache_strategies import CacheWarmingStrategy

        # Mock cache service
        mock_cache = Mock()
        mock_cache.cache_week_availability.return_value = True

        # Create warming strategy
        strategy = CacheWarmingStrategy(mock_cache, db)

        # FIXED: Patch the actual import location inside the method
        with patch.object(strategy, "db") as mock_db:
            # Mock the availability service that will be created
            mock_service = Mock()
            mock_service.get_week_availability.return_value = {
                "2025-07-14": [{"id": 1, "start_time": "09:00", "end_time": "10:00"}]
            }

            # Patch where AvailabilityService is imported inside the method
            with patch("app.services.cache_strategies.AvailabilityService") as mock_service_class:
                mock_service_class.return_value = mock_service

                # Warm cache
                result = await strategy.warm_with_verification(
                    instructor_id=123, week_start=date(2025, 7, 14), expected_slot_count=1
                )

                # Verify it used service layer
                mock_service_class.assert_called_with(strategy.db, None)  # No cache passed
                mock_service.get_week_availability.assert_called_with(123, date(2025, 7, 14))

    @pytest.mark.asyncio
    async def test_cache_warming_handles_clean_data(self, db):
        """Test cache warming handles data without removed fields."""
        from app.services.cache_strategies import CacheWarmingStrategy

        mock_cache = Mock()
        strategy = CacheWarmingStrategy(mock_cache, db)

        # Mock availability data (clean format)
        clean_data = {
            "2025-07-14": [
                {
                    "id": 1,
                    "instructor_id": 123,
                    "date": "2025-07-14",
                    "start_time": "09:00",
                    "end_time": "12:00",
                    # NO availability_slot_id
                    # NO is_available
                }
            ]
        }

        # FIXED: Patch at the correct import location
        with patch("app.services.cache_strategies.AvailabilityService") as mock_service_class:
            mock_service = Mock()
            mock_service.get_week_availability.return_value = clean_data
            mock_service_class.return_value = mock_service

            # Warm cache
            result = await strategy.warm_with_verification(instructor_id=123, week_start=date(2025, 7, 14))

            # Verify clean data was cached
            mock_cache.cache_week_availability.assert_called_with(123, date(2025, 7, 14), clean_data)

            # Result should be clean
            assert result == clean_data
            for date_str, slots in result.items():
                for slot in slots:
                    assert "availability_slot_id" not in slot
                    assert "is_available" not in slot


class TestCacheIntegration:
    """Integration tests for cache with clean architecture."""

    def test_cache_stats_dont_reference_removed_concepts(self, db):
        """Test cache statistics don't include removed concepts."""
        # FIXED: Remove incompatible Redis parameters
        # Create cache service without specifying Redis connection parameters
        # that might not be compatible with the version being used
        cache_service = CacheService(db)  # Let it use defaults
        stats = cache_service.get_stats()

        # Stats should be about cache performance
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats

        # Should NOT have slot-specific stats
        assert "slot_hits" not in stats
        assert "availability_slot_cache" not in stats

    def test_cache_ttl_tiers_are_business_focused(self):
        """Test cache TTL tiers are based on business concepts."""
        tiers = CacheService.TTL_TIERS

        # Tiers should be about access patterns, not data types
        assert "hot" in tiers  # Frequently accessed
        assert "warm" in tiers  # Moderate access
        assert "cold" in tiers  # Infrequent access
        assert "static" in tiers  # Rarely changes

        # Should NOT have slot-specific tiers
        assert "slot" not in str(tiers).lower()
        assert "availability_slot" not in str(tiers).lower()

    def test_circuit_breaker_works_without_slot_logic(self, db):
        """Test circuit breaker pattern doesn't involve slot logic."""
        from app.services.cache_service import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Test normal operation
        def good_operation():
            return "success"

        result = breaker.call(good_operation)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

        # Circuit breaker is infrastructure - shouldn't know about slots
        assert not hasattr(breaker, "slot_threshold")
        assert not hasattr(breaker, "availability_checks")
