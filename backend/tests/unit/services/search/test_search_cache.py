# backend/tests/unit/services/search/test_search_cache.py
"""
Unit tests for search caching layer.

Tests multi-layer caching:
1. Response cache with version-based invalidation
2. Parsed query cache with serialization
3. Location cache with normalization
"""
from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any, Dict
from unittest.mock import Mock

import pytest

from app.services.search.query_parser import ParsedQuery
from app.services.search.search_cache import (
    LOCATION_CACHE_TTL,
    PARSED_CACHE_TTL,
    RESPONSE_CACHE_TTL,
    VERSION_KEY,
    CachedLocation,
    SearchCacheService,
)


@pytest.fixture
def mock_cache_service() -> Mock:
    """Create mock cache service."""
    cache = Mock()
    cache.get = Mock(return_value=None)
    cache.set = Mock(return_value=True)
    cache.redis = Mock()
    cache.redis.incr = Mock(return_value=2)
    return cache


@pytest.fixture
def search_cache(mock_cache_service: Mock) -> SearchCacheService:
    """Create search cache with mock."""
    return SearchCacheService(cache_service=mock_cache_service)


class TestResponseCache:
    """Tests for response caching."""

    def test_cache_miss_returns_none(self, search_cache: SearchCacheService) -> None:
        """Cache miss should return None."""
        result = search_cache.get_cached_response("piano lessons")
        assert result is None

    def test_cache_hit_returns_response(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Cache hit should return response dict."""
        cached_response = {"results": [{"name": "Piano Lessons"}]}

        # First call gets version, second call gets response
        mock_cache_service.get = Mock(side_effect=["1", json.dumps(cached_response)])

        result = search_cache.get_cached_response("piano lessons")

        assert result == cached_response

    def test_caches_response_with_ttl(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Response should be cached with correct TTL."""
        response: Dict[str, Any] = {"results": [{"name": "Test"}]}

        search_cache.cache_response("piano", response)

        # Verify set was called with correct TTL
        call_args = mock_cache_service.set.call_args
        assert call_args.kwargs["ttl"] == RESPONSE_CACHE_TTL

    def test_cache_key_includes_version(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Cache key should include version number."""
        mock_cache_service.get = Mock(return_value="42")

        key = search_cache._response_cache_key("piano", None, None)

        assert "v42" in key

    def test_cache_key_different_for_different_locations(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Different locations should produce different cache keys."""
        mock_cache_service.get = Mock(return_value="1")

        key1 = search_cache._response_cache_key("piano", (-73.95, 40.68), None)
        key2 = search_cache._response_cache_key("piano", (-74.00, 40.70), None)

        assert key1 != key2

    def test_cache_key_same_for_same_query(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Same query should produce same cache key."""
        mock_cache_service.get = Mock(return_value="1")

        key1 = search_cache._response_cache_key("piano", None, None)
        key2 = search_cache._response_cache_key("piano", None, None)

        assert key1 == key2

    def test_invalidation_increments_version(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Invalidation should increment version."""
        mock_cache_service.redis.incr = Mock(return_value=5)

        new_version = search_cache.invalidate_response_cache()

        assert new_version == 5
        mock_cache_service.redis.incr.assert_called_once_with(VERSION_KEY)


class TestParsedQueryCache:
    """Tests for parsed query caching."""

    def test_cache_miss_returns_none(self, search_cache: SearchCacheService) -> None:
        """Cache miss should return None."""
        result = search_cache.get_cached_parsed_query("piano")
        assert result is None

    def test_caches_and_retrieves_parsed_query(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Should cache and retrieve parsed query correctly."""
        parsed = ParsedQuery(
            original_query="piano under $50",
            service_query="piano",
            max_price=50,
            parsing_mode="regex",
        )

        # Cache it
        search_cache.cache_parsed_query("piano under $50", parsed)

        # Mock retrieval
        cached_json = search_cache._serialize_parsed_query(parsed)
        mock_cache_service.get = Mock(return_value=cached_json)

        # Retrieve it
        result = search_cache.get_cached_parsed_query("piano under $50")

        assert result is not None
        assert result.service_query == "piano"
        assert result.max_price == 50

    def test_parsed_cache_ttl(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Parsed query should be cached with correct TTL."""
        parsed = ParsedQuery(
            original_query="test",
            service_query="test",
            parsing_mode="regex",
        )

        search_cache.cache_parsed_query("test", parsed)

        call_args = mock_cache_service.set.call_args
        assert call_args.kwargs["ttl"] == PARSED_CACHE_TTL

    def test_serializes_dates_correctly(self, search_cache: SearchCacheService) -> None:
        """Dates should serialize and deserialize correctly."""
        parsed = ParsedQuery(
            original_query="piano tomorrow",
            service_query="piano",
            date=date.today() + timedelta(days=1),
            date_type="single",
            parsing_mode="regex",
        )

        serialized = search_cache._serialize_parsed_query(parsed)
        deserialized = search_cache._deserialize_parsed_query(serialized)

        assert deserialized.date == parsed.date

    def test_serializes_date_range_correctly(self, search_cache: SearchCacheService) -> None:
        """Date ranges should serialize and deserialize correctly."""
        parsed = ParsedQuery(
            original_query="piano this weekend",
            service_query="piano",
            date_range_start=date.today(),
            date_range_end=date.today() + timedelta(days=2),
            date_type="range",
            parsing_mode="regex",
        )

        serialized = search_cache._serialize_parsed_query(parsed)
        deserialized = search_cache._deserialize_parsed_query(serialized)

        assert deserialized.date_range_start == parsed.date_range_start
        assert deserialized.date_range_end == parsed.date_range_end


class TestLocationCache:
    """Tests for location caching."""

    def test_cache_miss_returns_none(self, search_cache: SearchCacheService) -> None:
        """Cache miss should return None."""
        result = search_cache.get_cached_location("Brooklyn")
        assert result is None

    def test_caches_and_retrieves_location(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Should cache and retrieve location correctly."""
        location = CachedLocation(
            lng=-73.95,
            lat=40.68,
            borough="Brooklyn",
            neighborhood="Park Slope",
        )

        # Cache it
        search_cache.cache_location("Park Slope", location)

        # Mock retrieval
        mock_cache_service.get = Mock(
            return_value=json.dumps(
                {
                    "lng": -73.95,
                    "lat": 40.68,
                    "borough": "Brooklyn",
                    "neighborhood": "Park Slope",
                }
            )
        )

        # Retrieve it
        result = search_cache.get_cached_location("Park Slope")

        assert result is not None
        assert result.lng == -73.95
        assert result.borough == "Brooklyn"

    def test_location_cache_ttl(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Location should be cached with correct TTL."""
        location = CachedLocation(lng=-73.95, lat=40.68)

        search_cache.cache_location("Brooklyn", location)

        call_args = mock_cache_service.set.call_args
        assert call_args.kwargs["ttl"] == LOCATION_CACHE_TTL

    def test_location_key_normalized(self, search_cache: SearchCacheService) -> None:
        """Location keys should be normalized (lowercase, trimmed)."""
        key1 = search_cache._location_cache_key("Brooklyn")
        key2 = search_cache._location_cache_key("BROOKLYN")
        key3 = search_cache._location_cache_key("  brooklyn  ")

        assert key1 == key2 == key3


class TestCacheWarming:
    """Tests for cache warming."""

    def test_warms_location_cache(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Should warm cache with provided locations."""
        locations = [
            {"name": "Brooklyn", "lng": -73.95, "lat": 40.68, "borough": "Brooklyn"},
            {"name": "Manhattan", "lng": -73.97, "lat": 40.78, "borough": "Manhattan"},
        ]

        count = search_cache.warm_location_cache(locations)

        assert count == 2
        assert mock_cache_service.set.call_count == 2

    def test_returns_zero_when_cache_unavailable(self) -> None:
        """Should return 0 when cache is unavailable."""
        cache = SearchCacheService(cache_service=None)

        count = cache.warm_location_cache([{"name": "Test", "lng": 0, "lat": 0}])

        assert count == 0


class TestCacheStats:
    """Tests for cache statistics."""

    def test_returns_stats(
        self, search_cache: SearchCacheService, mock_cache_service: Mock
    ) -> None:
        """Should return cache stats."""
        mock_cache_service.get = Mock(return_value="5")

        stats = search_cache.get_cache_stats()

        assert stats["available"] is True
        assert stats["response_cache_version"] == 5
        assert "ttls" in stats

    def test_handles_unavailable_cache(self) -> None:
        """Should handle unavailable cache gracefully."""
        cache = SearchCacheService(cache_service=None)

        stats = cache.get_cache_stats()

        assert stats["available"] is False


class TestGracefulDegradation:
    """Tests for graceful handling of cache failures."""

    def test_returns_none_when_cache_unavailable(self) -> None:
        """Should return None when cache is unavailable."""
        cache = SearchCacheService(cache_service=None)

        result = cache.get_cached_response("piano")

        assert result is None

    def test_returns_false_when_cache_write_fails(self, mock_cache_service: Mock) -> None:
        """Should return False when cache write fails."""
        mock_cache_service.get = Mock(return_value="1")
        mock_cache_service.set = Mock(side_effect=Exception("Connection error"))
        cache = SearchCacheService(cache_service=mock_cache_service)

        result = cache.cache_response("piano", {"results": []})

        assert result is False

    def test_parsed_cache_returns_none_when_unavailable(self) -> None:
        """Parsed cache should return None when unavailable."""
        cache = SearchCacheService(cache_service=None)

        result = cache.get_cached_parsed_query("piano")

        assert result is None

    def test_location_cache_returns_none_when_unavailable(self) -> None:
        """Location cache should return None when unavailable."""
        cache = SearchCacheService(cache_service=None)

        result = cache.get_cached_location("Brooklyn")

        assert result is None


class TestResponseSerialization:
    """Tests for response serialization with dates."""

    def test_serializes_dates_in_response(self, search_cache: SearchCacheService) -> None:
        """Should serialize dates in response correctly."""
        response = {
            "results": [{"earliest_available": date.today(), "available_dates": [date.today()]}]
        }

        serialized = search_cache._serialize_response(response)
        deserialized = search_cache._deserialize_response(serialized)

        # Dates become ISO strings after round-trip
        assert date.today().isoformat() in serialized
        assert isinstance(deserialized["results"][0]["earliest_available"], str)

    def test_handles_nested_dicts_and_lists(self, search_cache: SearchCacheService) -> None:
        """Should handle nested structures correctly."""
        response: Dict[str, Any] = {
            "results": [{"scores": {"quality": 0.9, "relevance": 0.8}, "tags": ["piano", "music"]}],
            "metadata": {"total": 10, "filters_applied": ["price", "location"]},
        }

        serialized = search_cache._serialize_response(response)
        deserialized = search_cache._deserialize_response(serialized)

        assert deserialized["results"][0]["scores"]["quality"] == 0.9
        assert deserialized["metadata"]["total"] == 10
