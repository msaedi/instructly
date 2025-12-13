# backend/tests/unit/services/search/test_query_parser.py
"""
Unit tests for the regex query parser.
"""
from datetime import date, timedelta
from typing import Dict, Tuple
from unittest.mock import Mock, patch

import pytest

from app.services.search.query_parser import QueryParser


class MockLocation:
    """Mock NYC location for testing."""

    def __init__(
        self, name: str, type: str, borough: str, aliases: list[str] | None = None
    ) -> None:
        self.name = name
        self.type = type
        self.borough = borough
        self.aliases = aliases or []


class MockPriceThreshold:
    """Mock price threshold for testing."""

    def __init__(self, category: str, intent: str, max_price: int) -> None:
        self.category = category
        self.intent = intent
        self.max_price = max_price


def _build_location_cache() -> Dict[str, Dict[str, str]]:
    """Build mock location cache."""
    mock_locations = [
        MockLocation("Brooklyn", "borough", "Brooklyn", ["bk", "bklyn"]),
        MockLocation("Manhattan", "borough", "Manhattan", ["nyc"]),
        MockLocation("Park Slope", "neighborhood", "Brooklyn", ["parkslope"]),
        MockLocation("Williamsburg", "neighborhood", "Brooklyn", ["wburg"]),
        MockLocation("Upper West Side", "neighborhood", "Manhattan", ["uws"]),
    ]
    cache: Dict[str, Dict[str, str]] = {}
    for loc in mock_locations:
        cache[loc.name.lower()] = {
            "name": loc.name,
            "type": loc.type,
            "borough": loc.borough,
        }
        if loc.aliases:
            for alias in loc.aliases:
                cache[alias.lower()] = {
                    "name": loc.name,
                    "type": loc.type,
                    "borough": loc.borough,
                }
    return cache


def _build_threshold_cache() -> Dict[Tuple[str, str], int]:
    """Build mock threshold cache."""
    mock_thresholds = [
        MockPriceThreshold("music", "budget", 60),
        MockPriceThreshold("music", "standard", 100),
        MockPriceThreshold("music", "premium", 999999),
        MockPriceThreshold("tutoring", "budget", 50),
        MockPriceThreshold("tutoring", "standard", 80),
        MockPriceThreshold("tutoring", "premium", 999999),
        MockPriceThreshold("general", "budget", 50),
        MockPriceThreshold("general", "standard", 80),
        MockPriceThreshold("general", "premium", 999999),
    ]
    cache: Dict[Tuple[str, str], int] = {}
    for t in mock_thresholds:
        cache[(t.category, t.intent)] = t.max_price
    return cache


@pytest.fixture
def mock_db() -> Mock:
    """Create mock database session."""
    return Mock()


@pytest.fixture
def parser(mock_db: Mock) -> QueryParser:
    """Create QueryParser with mock database and mocked repositories."""
    with (
        patch(
            "app.repositories.nl_search_repository.NYCLocationRepository.build_location_cache"
        ) as mock_loc,
        patch(
            "app.repositories.nl_search_repository.PriceThresholdRepository.build_threshold_cache"
        ) as mock_price,
    ):
        mock_loc.return_value = _build_location_cache()
        mock_price.return_value = _build_threshold_cache()
        p = QueryParser(mock_db)
        # Pre-populate the caches to avoid repository calls during tests
        p._location_cache = _build_location_cache()
        p._price_thresholds = _build_threshold_cache()
        return p


class TestPriceExtraction:
    """Tests for price pattern extraction."""

    def test_explicit_dollar_under(self, parser: QueryParser) -> None:
        result = parser.parse("piano lessons under $50")
        assert result.max_price == 50
        assert "piano" in result.service_query.lower()

    def test_explicit_dollar_less_than(self, parser: QueryParser) -> None:
        result = parser.parse("guitar less than $100")
        assert result.max_price == 100

    def test_price_per_hour(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring $75/hr")
        assert result.max_price == 75

    def test_price_dollars_word(self, parser: QueryParser) -> None:
        result = parser.parse("lessons 50 dollars")
        assert result.max_price == 50

    def test_implicit_under_high_number(self, parser: QueryParser) -> None:
        """Numbers >= 20 without kid context are prices."""
        result = parser.parse("piano under 50")
        assert result.max_price == 50

    def test_implicit_under_age_context(self, parser: QueryParser) -> None:
        """Numbers <= 18 with kid context are NOT prices."""
        result = parser.parse("lessons for kids under 5")
        assert result.max_price is None
        assert result.audience_hint == "kids"

    def test_budget_keyword(self, parser: QueryParser) -> None:
        result = parser.parse("cheap piano lessons")
        assert result.price_intent == "budget"
        # Should resolve to category-specific threshold
        assert result.max_price == 60  # music budget threshold

    def test_affordable_keyword(self, parser: QueryParser) -> None:
        result = parser.parse("affordable tutoring")
        assert result.price_intent == "budget"
        assert result.max_price == 50  # tutoring budget threshold

    def test_premium_keyword(self, parser: QueryParser) -> None:
        result = parser.parse("premium tutoring")
        assert result.price_intent == "premium"


class TestAudienceExtraction:
    """Tests for audience hint extraction."""

    def test_year_old_pattern(self, parser: QueryParser) -> None:
        result = parser.parse("piano for 8 year old")
        assert result.audience_hint == "kids"

    def test_age_explicit(self, parser: QueryParser) -> None:
        result = parser.parse("lessons age 12")
        assert result.audience_hint == "kids"

    def test_for_my_child(self, parser: QueryParser) -> None:
        result = parser.parse("guitar for my 6 year old son")
        assert result.audience_hint == "kids"

    def test_kids_keyword(self, parser: QueryParser) -> None:
        result = parser.parse("piano for kids")
        assert result.audience_hint == "kids"

    def test_teens_keyword(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring for teenagers")
        assert result.audience_hint == "kids"  # teens -> kids category

    def test_adults_keyword(self, parser: QueryParser) -> None:
        result = parser.parse("yoga for adults")
        assert result.audience_hint == "adults"

    def test_adult_age(self, parser: QueryParser) -> None:
        result = parser.parse("lessons for 25 year old")
        assert result.audience_hint == "adults"


class TestTimeExtraction:
    """Tests for time pattern extraction."""

    def test_after_pm(self, parser: QueryParser) -> None:
        result = parser.parse("piano after 5pm")
        assert result.time_after == "17:00"

    def test_before_pm(self, parser: QueryParser) -> None:
        result = parser.parse("lessons before 3pm")
        assert result.time_before == "15:00"

    def test_at_time(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring at 10am")
        assert result.time_after == "10:00"

    def test_morning_window(self, parser: QueryParser) -> None:
        result = parser.parse("yoga morning")
        assert result.time_window == "morning"
        assert result.time_after == "06:00"
        assert result.time_before == "12:00"

    def test_evening_window(self, parser: QueryParser) -> None:
        result = parser.parse("guitar lessons evening")
        assert result.time_window == "evening"
        assert result.time_after == "17:00"
        assert result.time_before == "21:00"

    def test_ambiguous_time_assumes_pm(self, parser: QueryParser) -> None:
        """Times 1-6 without meridiem assume PM."""
        result = parser.parse("lessons after 5")
        assert result.time_after == "17:00"


class TestDateExtraction:
    """Tests for date pattern extraction."""

    def test_tomorrow(self, parser: QueryParser) -> None:
        result = parser.parse("piano tomorrow")
        expected = date.today() + timedelta(days=1)
        assert result.date == expected
        assert result.date_type == "single"

    def test_today(self, parser: QueryParser) -> None:
        result = parser.parse("lessons today")
        assert result.date == date.today()

    def test_this_weekend(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring this weekend")
        assert result.date_type == "weekend"
        assert result.date_range_start is not None
        assert result.date_range_end is not None
        # Weekend should be Sat/Sun
        assert result.date_range_end - result.date_range_start == timedelta(days=1)


class TestLocationExtraction:
    """Tests for location pattern extraction."""

    def test_in_brooklyn(self, parser: QueryParser) -> None:
        result = parser.parse("piano in brooklyn")
        assert result.location_text == "Brooklyn"
        assert result.location_type == "borough"

    def test_near_park_slope(self, parser: QueryParser) -> None:
        result = parser.parse("lessons near park slope")
        assert result.location_text == "Park Slope"
        assert result.location_type == "neighborhood"

    def test_near_me(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring near me")
        assert result.location_type == "near_me"

    def test_location_alias(self, parser: QueryParser) -> None:
        result = parser.parse("guitar in bk")
        assert result.location_text == "Brooklyn"


class TestSkillLevel:
    """Tests for skill level extraction."""

    def test_beginner(self, parser: QueryParser) -> None:
        result = parser.parse("beginner piano lessons")
        assert result.skill_level == "beginner"

    def test_advanced(self, parser: QueryParser) -> None:
        result = parser.parse("advanced guitar")
        assert result.skill_level == "advanced"

    def test_intermediate(self, parser: QueryParser) -> None:
        result = parser.parse("intermediate swimming")
        assert result.skill_level == "intermediate"


class TestUrgency:
    """Tests for urgency extraction."""

    def test_urgent(self, parser: QueryParser) -> None:
        result = parser.parse("urgent piano lessons needed")
        assert result.urgency == "high"

    def test_asap(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring asap")
        assert result.urgency == "high"

    def test_soon(self, parser: QueryParser) -> None:
        result = parser.parse("need lessons soon")
        assert result.urgency == "medium"


class TestComplexQueries:
    """Tests for complex query handling."""

    def test_full_query(self, parser: QueryParser) -> None:
        """Test a complex query with multiple constraints."""
        result = parser.parse(
            "cheap piano lessons tomorrow after 5pm in brooklyn for my 8 year old"
        )

        assert result.price_intent == "budget" or result.max_price is not None
        assert result.date == date.today() + timedelta(days=1)
        assert result.time_after == "17:00"
        assert result.location_text == "Brooklyn"
        assert result.audience_hint == "kids"
        assert "piano" in result.service_query.lower()

    def test_needs_llm_for_conditional(self, parser: QueryParser) -> None:
        result = parser.parse("piano or guitar lessons")
        assert result.needs_llm is True

    def test_needs_llm_for_context_reference(self, parser: QueryParser) -> None:
        result = parser.parse("same as last time")
        assert result.needs_llm is True

    def test_simple_query_no_llm(self, parser: QueryParser) -> None:
        result = parser.parse("piano lessons brooklyn")
        assert result.needs_llm is False


class TestEdgeCases:
    """Tests for edge cases and disambiguation."""

    def test_kids_under_5_not_price(self, parser: QueryParser) -> None:
        """Regression test: 'kids under 5' should NOT extract price."""
        result = parser.parse("lessons for kids under 5")
        assert result.max_price is None
        assert result.audience_hint == "kids"

    def test_under_50_is_price(self, parser: QueryParser) -> None:
        """'under 50' without kid context IS a price."""
        result = parser.parse("piano under 50")
        assert result.max_price == 50

    def test_empty_query(self, parser: QueryParser) -> None:
        result = parser.parse("")
        assert result.service_query == ""
        assert result.original_query == ""

    def test_only_constraints_no_service(self, parser: QueryParser) -> None:
        result = parser.parse("tomorrow after 5pm in brooklyn")
        # Should still work, service_query will be minimal
        assert result.date is not None
        assert result.time_after == "17:00"
        assert result.location_text == "Brooklyn"

    def test_preserves_original_query(self, parser: QueryParser) -> None:
        original = "Piano Lessons Under $50 Tomorrow"
        result = parser.parse(original)
        assert result.original_query == original


class TestParsingPerformance:
    """Tests for parsing performance."""

    def test_parsing_latency_recorded(self, parser: QueryParser) -> None:
        result = parser.parse("piano lessons")
        assert result.parsing_latency_ms >= 0

    def test_parsing_latency_under_10ms(self, parser: QueryParser) -> None:
        """Regex parsing should be sub-10ms."""
        # Run multiple times to warm up
        for _ in range(5):
            parser.parse("cheap piano lessons tomorrow after 5pm in brooklyn")

        # Measure
        result = parser.parse("cheap piano lessons tomorrow after 5pm in brooklyn")
        assert result.parsing_latency_ms < 10, (
            f"Parsing took {result.parsing_latency_ms}ms, expected < 10ms"
        )

    def test_parsing_mode_is_regex(self, parser: QueryParser) -> None:
        result = parser.parse("piano lessons")
        assert result.parsing_mode == "regex"

    def test_confidence_high_for_simple(self, parser: QueryParser) -> None:
        result = parser.parse("piano lessons brooklyn")
        assert result.confidence >= 0.9

    def test_confidence_lower_for_complex(self, parser: QueryParser) -> None:
        result = parser.parse("piano or guitar lessons either works")
        assert result.confidence < 0.9
