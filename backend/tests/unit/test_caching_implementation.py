# backend/tests/unit/test_caching_implementation.py
"""
Unit tests for caching implementation.

Tests the repository-level and service-level caching functionality
to ensure proper cache hits, misses, and invalidation.
"""

from datetime import date, datetime, time
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.models.booking import Booking, BookingStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.cached_repository_mixin import CachedRepositoryMixin
from app.services.booking_service import BookingService
from app.services.cache_service import CacheService


class TestRepositoryCaching:
    """Test repository-level caching functionality."""

    def test_cache_mixin_initialization(self, db_session):
        """Test that cached repository mixin initializes correctly."""
        # Create a repository with caching
        repo = BookingRepository(db_session)

        # Verify cache initialization
        assert hasattr(repo, "_cache_service")
        assert hasattr(repo, "_cache_prefix")
        assert repo._cache_prefix == "booking"
        assert repo._cache_enabled is True

    def test_cache_result_decorator_hit(self, db_session):
        """Test cache hit with @cache_result decorator."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)
        mock_cache.get.return_value = [{"id": 1, "status": "CONFIRMED"}]  # Cached result

        # Create repository with mock cache
        repo = BookingRepository(db_session, cache_service=mock_cache)

        # Call a cached method
        result = repo.get_student_bookings(student_id=123)

        # Verify cache was checked
        mock_cache.get.assert_called_once()
        # Verify database was NOT queried (would fail since we have mock data)
        assert result == [{"id": 1, "status": "CONFIRMED"}]

    def test_cache_result_decorator_miss(self, db_session):
        """Test cache miss with @cache_result decorator."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)
        mock_cache.get.return_value = None  # Cache miss

        # Create repository with mock cache
        repo = BookingRepository(db_session, cache_service=mock_cache)

        # Mock the database query
        with patch.object(repo.db, "query") as mock_query:
            mock_query.return_value.options.return_value.filter.return_value.all.return_value = []

            # Call a cached method
            result = repo.get_student_bookings(student_id=123)

            # Verify cache was checked
            mock_cache.get.assert_called_once()
            # Verify result was cached
            mock_cache.set.assert_called_once()
            # Verify database was queried
            mock_query.assert_called_once()

    def test_cache_invalidation_on_update(self, db_session):
        """Test that cache is invalidated when booking is updated."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)

        # Create repository with mock cache
        repo = BookingRepository(db_session, cache_service=mock_cache)

        # Mock booking
        booking = Mock(spec=Booking)
        booking.id = 1
        booking.student_id = 123
        booking.instructor_id = 456
        booking.status = BookingStatus.CONFIRMED
        booking.completed_at = None

        # Mock get_by_id to return our booking
        with patch.object(repo, "get_by_id", return_value=booking):
            # Complete the booking
            repo.complete_booking(booking_id=1)

            # Verify cache invalidation was called for all related entities
            assert mock_cache.delete_pattern.call_count >= 3  # booking, student, instructor

    def test_cache_key_generation(self):
        """Test cache key generation for different method calls."""
        mixin = CachedRepositoryMixin()
        mixin._cache_prefix = "test"

        # Test simple key generation
        key = mixin._generate_cache_key("get_by_id", 123)
        assert key == "test:get_by_id:123"

        # Test key with multiple args
        key = mixin._generate_cache_key("get_bookings", 123, date(2025, 1, 1))
        assert key == "test:get_bookings:123:2025-01-01"

        # Test key with kwargs
        key = mixin._generate_cache_key("search", status="CONFIRMED", limit=10)
        assert "test:search:kw_" in key  # Should include hashed kwargs


class TestServiceCaching:
    """Test service-level caching functionality."""

    def test_booking_stats_cache_hit(self, db_session):
        """Test that booking stats are cached at service level."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)
        cached_stats = {"total_bookings": 10, "upcoming_bookings": 3, "completed_bookings": 7, "total_earnings": 1500.0}
        mock_cache.get.return_value = cached_stats

        # Create service with mock cache
        service = BookingService(
            db=db_session, cache_service=mock_cache, notification_service=Mock(), repository=Mock()
        )

        # Get stats
        stats = service.get_booking_stats_for_instructor(instructor_id=123)

        # Verify cache was checked
        mock_cache.get.assert_called_once_with("booking_stats:instructor:123")
        # Verify cached result was returned
        assert stats == cached_stats
        # Verify repository was NOT called
        assert service.repository.get_instructor_bookings_for_stats.call_count == 0

    def test_booking_stats_cache_miss(self, db_session):
        """Test that booking stats are calculated and cached on miss."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)
        mock_cache.get.return_value = None  # Cache miss

        # Create mock repository
        mock_repo = Mock()
        mock_bookings = [
            Mock(is_upcoming=False, status=BookingStatus.COMPLETED, total_price=100.0, booking_date=date.today())
            for _ in range(5)
        ]
        mock_repo.get_instructor_bookings_for_stats.return_value = mock_bookings

        # Create service
        service = BookingService(
            db=db_session, cache_service=mock_cache, notification_service=Mock(), repository=mock_repo
        )

        # Get stats
        stats = service.get_booking_stats_for_instructor(instructor_id=123)

        # Verify cache miss flow
        mock_cache.get.assert_called_once_with("booking_stats:instructor:123")
        mock_repo.get_instructor_bookings_for_stats.assert_called_once_with(123)
        # Verify result was cached
        mock_cache.set.assert_called_once()
        cache_call_args = mock_cache.set.call_args
        assert cache_call_args[0][0] == "booking_stats:instructor:123"
        assert cache_call_args[1]["tier"] == "hot"

        # Verify stats calculation
        assert stats["total_bookings"] == 5
        assert stats["completed_bookings"] == 5
        assert stats["total_earnings"] == 500.0

    def test_cache_invalidation_on_booking_change(self, db_session):
        """Test that stats cache is invalidated when booking changes."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)

        # Create mock booking
        mock_booking = Mock(spec=Booking)
        mock_booking.instructor_id = 123
        mock_booking.student_id = 456
        mock_booking.booking_date = date.today()

        # Create service
        service = BookingService(
            db=db_session, cache_service=mock_cache, notification_service=Mock(), repository=Mock()
        )

        # Invalidate caches
        service._invalidate_booking_caches(mock_booking)

        # Verify stats caches were invalidated
        cache_deletes = [call[0][0] for call in mock_cache.delete.call_args_list]
        assert "booking_stats:instructor:123" in cache_deletes
        assert "booking_stats:student:456" in cache_deletes

        # Verify availability cache was invalidated
        mock_cache.invalidate_instructor_availability.assert_called_once_with(123, [mock_booking.booking_date])

    def test_cache_disabled_context_manager(self, db_session):
        """Test that caching can be temporarily disabled."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)
        mock_cache.get.return_value = {"cached": True}

        # Create repository with mock cache
        repo = BookingRepository(db_session, cache_service=mock_cache)

        # Use cache disabled context
        with repo.with_cache_disabled():
            assert repo._cache_enabled is False

            # Mock the database query
            with patch.object(repo.db, "query") as mock_query:
                mock_query.return_value.options.return_value.filter.return_value.all.return_value = []

                # Call a cached method
                result = repo.get_student_bookings(student_id=123)

                # Verify cache was NOT used
                mock_cache.get.assert_not_called()
                mock_cache.set.assert_not_called()
                # Verify database was queried directly
                mock_query.assert_called_once()

        # Verify cache is re-enabled after context
        assert repo._cache_enabled is True


class TestCachePerformance:
    """Test cache performance improvements."""

    def test_repository_cache_reduces_database_queries(self, db_session):
        """Test that repository caching reduces database query count."""
        # Create repository with real cache service
        repo = BookingRepository(db_session)

        # Track query count
        query_count = 0
        original_query = repo.db.query

        def counting_query(*args, **kwargs):
            nonlocal query_count
            query_count += 1
            return original_query(*args, **kwargs)

        repo.db.query = counting_query

        # First call - should hit database
        with patch.object(repo.db.query(Booking), "all", return_value=[]):
            repo.get_student_bookings(student_id=123)
            first_query_count = query_count

        # Second call - should hit cache if enabled
        if repo._cache_service:
            repo.get_student_bookings(student_id=123)
            second_query_count = query_count

            # With caching, second call should not increase query count
            assert second_query_count == first_query_count

    def test_service_cache_reduces_computation(self, db_session):
        """Test that service caching reduces expensive computations."""
        # Create service with cache
        mock_cache = Mock(spec=CacheService)
        mock_cache.get.side_effect = [None, {"cached": True}]  # First miss, then hit

        mock_repo = Mock()
        # Expensive operation (lots of bookings)
        mock_repo.get_instructor_bookings_for_stats.return_value = [
            Mock(is_upcoming=False, status=BookingStatus.COMPLETED, total_price=100.0, booking_date=date.today())
            for _ in range(1000)
        ]

        service = BookingService(
            db=db_session, cache_service=mock_cache, notification_service=Mock(), repository=mock_repo
        )

        # First call - expensive computation
        stats1 = service.get_booking_stats_for_instructor(instructor_id=123)
        assert mock_repo.get_instructor_bookings_for_stats.call_count == 1

        # Second call - should use cache
        stats2 = service.get_booking_stats_for_instructor(instructor_id=123)
        # Repository should not be called again
        assert mock_repo.get_instructor_bookings_for_stats.call_count == 1
