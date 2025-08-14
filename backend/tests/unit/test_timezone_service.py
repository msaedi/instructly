"""
Unit tests for TimezoneService using prefix mapping.
Tests the ZIP code prefix-based timezone detection.
"""

from unittest.mock import patch

import pytest

from app.core.timezone_service import (
    cache_info,
    clear_cache,
    get_timezone_from_zip,
    get_timezone_offset,
    validate_timezone,
)


class TestTimezoneService:
    """Test cases for timezone service with prefix mapping."""

    def test_nyc_timezone(self):
        """Test NYC ZIP codes return Eastern time."""
        assert get_timezone_from_zip("10001") == "America/New_York"
        assert get_timezone_from_zip("10013") == "America/New_York"
        assert get_timezone_from_zip("11201") == "America/New_York"  # Brooklyn

    def test_la_timezone(self):
        """Test LA ZIP codes return Pacific time."""
        assert get_timezone_from_zip("90210") == "America/Los_Angeles"
        assert get_timezone_from_zip("90001") == "America/Los_Angeles"

    def test_chicago_timezone(self):
        """Test Chicago ZIP codes return Central time."""
        assert get_timezone_from_zip("60601") == "America/Chicago"
        assert get_timezone_from_zip("60611") == "America/Chicago"

    def test_denver_timezone(self):
        """Test Denver ZIP codes return Mountain time."""
        assert get_timezone_from_zip("80202") == "America/Denver"
        assert get_timezone_from_zip("80214") == "America/Denver"

    def test_phoenix_timezone(self):
        """Test Phoenix ZIP codes return Arizona time (no DST)."""
        assert get_timezone_from_zip("85001") == "America/Phoenix"
        assert get_timezone_from_zip("85251") == "America/Phoenix"  # Scottsdale

    def test_alaska_timezone(self):
        """Test Alaska ZIP codes."""
        assert get_timezone_from_zip("99501") == "America/Anchorage"
        assert get_timezone_from_zip("99577") == "America/Anchorage"

    def test_hawaii_timezone(self):
        """Test Hawaii ZIP codes."""
        assert get_timezone_from_zip("96801") == "Pacific/Honolulu"
        assert get_timezone_from_zip("96815") == "Pacific/Honolulu"

    def test_invalid_zip(self):
        """Test invalid ZIP codes return NYC default."""
        assert get_timezone_from_zip("invalid") == "America/New_York"
        assert get_timezone_from_zip("") == "America/New_York"
        assert get_timezone_from_zip(None) == "America/New_York"
        assert get_timezone_from_zip("12") == "America/New_York"  # Too short

    def test_zip_with_plus_four(self):
        """Test ZIP+4 format works."""
        assert get_timezone_from_zip("10001-1234") == "America/New_York"
        assert get_timezone_from_zip("90210-5678") == "America/Los_Angeles"

    def test_lru_caching(self):
        """Test that results are cached using @lru_cache."""
        # Clear cache to start fresh
        clear_cache()

        # Get initial cache info
        info_before = cache_info()
        initial_hits = info_before.hits
        initial_misses = info_before.misses

        # First call should be a cache miss
        tz1 = get_timezone_from_zip("10001")
        assert tz1 == "America/New_York"
        info_after_first = cache_info()
        assert info_after_first.misses == initial_misses + 1
        assert info_after_first.hits == initial_hits

        # Second call with same ZIP should be a cache hit
        tz2 = get_timezone_from_zip("10001")
        assert tz2 == "America/New_York"
        info_after_second = cache_info()
        assert info_after_second.hits == initial_hits + 1
        assert info_after_second.misses == initial_misses + 1

    def test_cache_different_zips(self):
        """Test caching works for different ZIP codes."""
        # Clear cache to start fresh
        clear_cache()

        # Multiple different ZIPs should each be cached
        zips_and_timezones = [
            ("10001", "America/New_York"),
            ("90210", "America/Los_Angeles"),
            ("60601", "America/Chicago"),
            ("80202", "America/Denver"),
        ]

        # First calls should all be misses
        for zip_code, expected_tz in zips_and_timezones:
            tz = get_timezone_from_zip(zip_code)
            assert tz == expected_tz

        info = cache_info()
        assert info.currsize == 4  # All 4 ZIPs cached

        # Second calls should all be hits
        initial_hits = info.hits
        for zip_code, expected_tz in zips_and_timezones:
            tz = get_timezone_from_zip(zip_code)
            assert tz == expected_tz

        info_after = cache_info()
        assert info_after.hits == initial_hits + 4  # All 4 were cache hits

    def test_clear_cache(self):
        """Test LRU cache clearing."""
        # Add some entries to cache
        get_timezone_from_zip("10001")
        get_timezone_from_zip("90210")
        get_timezone_from_zip("60601")

        # Verify cache has entries
        info_before = cache_info()
        assert info_before.currsize > 0

        # Clear cache
        clear_cache()

        # Verify cache is empty
        info_after = cache_info()
        assert info_after.currsize == 0
        assert info_after.hits == 0
        assert info_after.misses == 0

    def test_module_functions(self):
        """Test module-level functions work correctly."""
        # All functions should work as module-level imports
        tz = get_timezone_from_zip("10001")
        assert tz == "America/New_York"

        # Validation function
        assert validate_timezone("America/New_York") is True
        assert validate_timezone("Invalid/Timezone") is False

        # Offset function
        assert get_timezone_offset("America/New_York") == -5
        assert get_timezone_offset("America/Los_Angeles") == -8

    def test_timezone_validation(self):
        """Test timezone validation."""
        assert validate_timezone("America/New_York") is True
        assert validate_timezone("America/Los_Angeles") is True
        assert validate_timezone("America/Chicago") is True
        assert validate_timezone("America/Denver") is True
        assert validate_timezone("America/Phoenix") is True
        assert validate_timezone("America/Anchorage") is True
        assert validate_timezone("Pacific/Honolulu") is True

        # Invalid timezones
        assert validate_timezone("Europe/London") is False
        assert validate_timezone("Invalid/Timezone") is False
        assert validate_timezone("") is False

    def test_timezone_offset(self):
        """Test timezone offset calculation."""
        assert get_timezone_offset("America/New_York") == -5
        assert get_timezone_offset("America/Chicago") == -6
        assert get_timezone_offset("America/Denver") == -7
        assert get_timezone_offset("America/Phoenix") == -7  # No DST
        assert get_timezone_offset("America/Los_Angeles") == -8
        assert get_timezone_offset("America/Anchorage") == -9
        assert get_timezone_offset("Pacific/Honolulu") == -10
        assert get_timezone_offset("Unknown/Timezone") == -5  # Default

    def test_edge_cases(self):
        """Test edge cases and special ZIP codes."""
        # Puerto Rico (00 prefix) - Eastern Time
        assert get_timezone_from_zip("00901") == "America/New_York"

        # US Virgin Islands (008 prefix) - Eastern Time
        assert get_timezone_from_zip("00801") == "America/New_York"

        # Military APO/FPO (09 prefix) - Eastern Time default
        assert get_timezone_from_zip("09001") == "America/New_York"

        # Kentucky border areas (40-42 prefix) - Central Time
        assert get_timezone_from_zip("40201") == "America/Chicago"  # Louisville (actually Central)

        # Indiana areas (46 prefix) - Central Time (in our simplified mapping)
        assert get_timezone_from_zip("46201") == "America/Chicago"  # Indianapolis (simplified to Central)
