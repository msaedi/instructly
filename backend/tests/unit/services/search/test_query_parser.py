# backend/tests/unit/services/search/test_query_parser.py
"""
Unit tests for the regex query parser.
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, Tuple
from unittest.mock import Mock, patch

import dateparser
import pytest

from app.services.search.query_parser import QueryParser

# Store reference to original dateparser.parse before patching
_original_dateparser_parse = dateparser.parse


def _dateparser_with_consistent_base(
    date_string: str, settings: Dict[str, Any] | None = None
) -> datetime | None:
    """Wrapper for dateparser.parse that uses date.today() as RELATIVE_BASE."""
    if settings is None:
        settings = {}
    # Set RELATIVE_BASE to current system time for consistent testing
    settings["RELATIVE_BASE"] = datetime.combine(date.today(), datetime.min.time())
    return _original_dateparser_parse(date_string, settings=settings)


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

    def __init__(
        self,
        category: str,
        intent: str,
        max_price: int | None = None,
        min_price: int | None = None,
    ) -> None:
        self.category = category
        self.intent = intent
        self.max_price = max_price
        self.min_price = min_price


def _build_location_cache() -> Dict[str, Dict[str, str]]:
    """Build mock location cache."""
    mock_locations = [
        MockLocation("Brooklyn", "borough", "Brooklyn", ["bk", "bklyn"]),
        MockLocation("Manhattan", "borough", "Manhattan", ["nyc"]),
        MockLocation("Park Slope", "neighborhood", "Brooklyn", ["parkslope"]),
        MockLocation("Williamsburg", "neighborhood", "Brooklyn", ["wburg"]),
        MockLocation("Upper West Side", "neighborhood", "Manhattan", ["uws"]),
        MockLocation("Lower East Side", "neighborhood", "Manhattan", ["les"]),
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


def _build_threshold_cache() -> Dict[Tuple[str, str], Dict[str, int | None]]:
    """Build mock threshold cache with proper dict structure."""
    mock_thresholds = [
        MockPriceThreshold("music", "budget", max_price=60),
        MockPriceThreshold("music", "standard", max_price=100),
        MockPriceThreshold("music", "premium", min_price=150),
        MockPriceThreshold("tutoring", "budget", max_price=50),
        MockPriceThreshold("tutoring", "standard", max_price=80),
        MockPriceThreshold("tutoring", "premium", min_price=100),
        MockPriceThreshold("general", "budget", max_price=50),
        MockPriceThreshold("general", "standard", max_price=80),
        MockPriceThreshold("general", "premium", min_price=100),
    ]
    cache: Dict[Tuple[str, str], Dict[str, int | None]] = {}
    for t in mock_thresholds:
        cache[(t.category, t.intent)] = {
            "max_price": t.max_price,
            "min_price": t.min_price,
        }
    return cache


@pytest.fixture
def mock_db() -> Mock:
    """Create mock database session."""
    return Mock()


@pytest.fixture(autouse=True)
def patch_dateparser() -> Any:
    """Patch dateparser.parse to use consistent RELATIVE_BASE for all tests."""
    with patch(
        "app.services.search.query_parser.dateparser.parse",
        side_effect=_dateparser_with_consistent_base,
    ):
        yield


@pytest.fixture
def parser(mock_db: Mock) -> QueryParser:
    """Create QueryParser with mock database and mocked repositories."""
    with patch(
        "app.repositories.nl_search_repository.PriceThresholdRepository.build_threshold_cache"
    ) as mock_price:
        mock_price.return_value = _build_threshold_cache()
        p = QueryParser(mock_db)
        # Pre-populate the cache to avoid repository calls during tests
        p._price_thresholds = _build_threshold_cache()
        # Mock _get_user_today to use date.today() for consistent timezone behavior
        p._get_user_today = lambda: date.today()
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

    def test_explicit_price_removes_budget_words(self, parser: QueryParser) -> None:
        """Regression: 'cheap ... under 120' must not keep 'cheap' in service_query."""
        result = parser.parse("cheap guitar lessons under 120")
        assert result.max_price == 120
        assert result.price_intent is None  # explicit price wins
        assert "cheap" not in result.service_query.lower()
        assert "guitar" in result.service_query.lower()


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
        assert result.time_before == "11:00"

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

    def test_specific_time_creates_window(self, parser: QueryParser) -> None:
        """'at 6am' should create a 1-hour window, not open-ended."""
        result = parser.parse("piano at 6am")
        assert result.time_after == "06:00"
        assert result.time_before == "07:00"


class TestDateExtraction:
    """Tests for date pattern extraction."""

    def test_tomorrow(self, parser: QueryParser) -> None:
        """Test 'tomorrow' parsing extracts correct date type."""
        result = parser.parse("piano tomorrow")

        # The date should be tomorrow relative to when test runs
        expected = date.today() + timedelta(days=1)
        assert result.date == expected
        assert result.date_type == "single"

    def test_today(self, parser: QueryParser) -> None:
        """Test 'today' parsing extracts correct date type."""
        result = parser.parse("lessons today")

        # The date should be today
        assert result.date == date.today()
        assert result.date_type == "single"

    def test_this_weekend(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring this weekend")
        assert result.date_type == "weekend"
        assert result.date_range_start is not None
        assert result.date_range_end is not None
        # Weekend should be Sat/Sun
        assert result.date_range_end - result.date_range_start == timedelta(days=1)

    def test_weekday_name_resolves_to_next_occurrence(self, parser: QueryParser) -> None:
        """Standalone weekday names should resolve to the next occurrence."""
        result = parser.parse("lessons monday afternoon")
        assert result.date is not None
        assert result.date.weekday() == 0  # Monday
        assert "monday" not in result.service_query.lower()

    def test_weekday_with_time(self, parser: QueryParser) -> None:
        """Weekday + time window should both be parsed."""
        result = parser.parse("piano lessons monday evening")
        assert result.date is not None
        assert result.date.weekday() == 0  # Monday
        assert result.time_after == "17:00"

    def test_weekday_abbreviations(self, parser: QueryParser) -> None:
        """Abbreviated weekdays should resolve to a concrete date."""
        cases = {
            "mon": 0,
            "tue": 1,
            "wed": 2,
            "thu": 3,
            "fri": 4,
            "sat": 5,
            "sun": 6,
        }
        for token, expected_weekday in cases.items():
            result = parser.parse(f"lessons {token}")
            assert result.date is not None
            assert result.date.weekday() == expected_weekday

    def test_next_weekday_is_at_least_7_days_out(self, parser: QueryParser) -> None:
        """'next <weekday>' should be at least a week away."""
        result = parser.parse("yoga next saturday")
        assert result.date is not None
        assert result.date.weekday() == 5  # Saturday
        assert result.date >= date.today() + timedelta(days=7)

    def test_sat_prep_not_interpreted_as_saturday(self, parser: QueryParser) -> None:
        """Regression: 'SAT prep' should not be parsed as a Saturday constraint."""
        result = parser.parse("SAT prep in brooklyn")
        assert result.date is None
        assert "sat" in result.service_query.lower()


class TestLocationExtraction:
    """Tests for location pattern extraction."""

    def test_in_brooklyn(self, parser: QueryParser) -> None:
        result = parser.parse("piano in brooklyn")
        assert result.location_text == "brooklyn"
        assert result.location_type == "borough"

    def test_near_park_slope(self, parser: QueryParser) -> None:
        result = parser.parse("lessons near park slope")
        assert result.location_text == "park slope"
        assert result.location_type == "neighborhood"

    def test_near_me(self, parser: QueryParser) -> None:
        result = parser.parse("tutoring near me")
        assert result.location_type == "near_me"

    def test_location_alias(self, parser: QueryParser) -> None:
        result = parser.parse("guitar in bk")
        assert result.location_text == "bk"

    def test_location_extraction_ues_not_corrupted(self, parser: QueryParser) -> None:
        """Regression: 'ues' must not become 'us for my' via typo correction + regex."""
        result = parser.parse("guitar lessons in ues for my kid under 150")
        assert result.location_text == "ues"
        assert result.audience_hint == "kids"
        assert result.max_price == 150
        assert "for my" not in result.service_query.lower()

    def test_location_extraction_lic_not_corrupted(self, parser: QueryParser) -> None:
        """Regression: SymSpell shouldn't turn 'lic' into a common word (e.g., 'pic')."""
        result = parser.parse("piano lessons in lic under 100")
        assert result.location_text == "lic"
        assert result.max_price == 100

    def test_in_the_morning_does_not_break_location(self, parser: QueryParser) -> None:
        """Regression: 'in the morning' shouldn't corrupt location extraction."""
        result = parser.parse("piano in ues tomorrow in the morning")
        assert result.location_text == "ues"
        assert result.time_after == "06:00"
        assert result.time_before == "12:00"
        assert "in the" not in result.service_query.lower()

    def test_multi_word_neighborhood_in(self, parser: QueryParser) -> None:
        result = parser.parse("guitar lessons in lower east side")
        assert result.location_text == "lower east side"
        assert result.location_type == "neighborhood"
        assert "lower" not in result.service_query.lower()
        assert "guitar" in result.service_query.lower()


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
        # Date should be tomorrow relative to when test runs
        assert result.date == date.today() + timedelta(days=1)
        assert result.time_after == "17:00"
        assert result.location_text == "brooklyn"
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
        assert result.location_text == "brooklyn"

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


class TestLessonTypeParsing:
    """Tests for lesson type (online/in-person) extraction."""

    @pytest.mark.parametrize(
        "query,expected_lesson_type",
        [
            # Online keywords
            ("online piano lessons", "online"),
            ("virtual guitar teacher", "online"),
            ("remote math tutoring", "online"),
            ("zoom yoga instructor", "online"),
            ("video piano lessons", "online"),
            ("webcam guitar lessons", "online"),
            # In-person keywords
            ("in-person piano lessons", "in_person"),
            ("in person guitar teacher", "in_person"),
            ("face-to-face math tutoring", "in_person"),
            ("face to face yoga", "in_person"),
            ("in-home piano lessons", "in_person"),
            ("at-home guitar teacher", "in_person"),
            ("at home yoga", "in_person"),
            # Default to any when no keyword
            ("piano lessons", "any"),
            ("guitar teacher brooklyn", "any"),
            ("math tutoring for kids", "any"),
        ],
    )
    def test_lesson_type_extraction(
        self, parser: QueryParser, query: str, expected_lesson_type: str
    ) -> None:
        result = parser.parse(query)
        assert result.lesson_type == expected_lesson_type

    def test_online_keyword_stripped_from_service_query(
        self, parser: QueryParser
    ) -> None:
        """Online/in-person keywords should be stripped from service_query."""
        result = parser.parse("online piano lessons")
        assert "online" not in result.service_query.lower()
        assert "piano" in result.service_query.lower()

    def test_in_person_keyword_stripped_from_service_query(
        self, parser: QueryParser
    ) -> None:
        """In-person keywords should be stripped from service_query."""
        result = parser.parse("in-person guitar lessons")
        assert "in-person" not in result.service_query.lower()
        assert "in person" not in result.service_query.lower()
        assert "guitar" in result.service_query.lower()

    def test_lesson_type_combined_with_other_constraints(
        self, parser: QueryParser
    ) -> None:
        """Lesson type should work with other constraints."""
        result = parser.parse("online piano lessons under 50 for kids")
        assert result.lesson_type == "online"
        assert result.max_price == 50
        assert result.audience_hint == "kids"
        assert "piano" in result.service_query.lower()


class TestNearMeLocation:
    """Tests for 'near me' location detection."""

    @pytest.mark.parametrize(
        "query,expected_use_user_location,expected_location_type",
        [
            ("piano lessons near me", True, "near_me"),
            ("guitar teacher nearby", True, "near_me"),
            ("math tutoring close by", True, "near_me"),
            ("yoga instructors close to me", True, "near_me"),
            ("piano lessons in my area", True, "near_me"),
            ("guitar teacher around me", True, "near_me"),
            ("tutors in my neighborhood", True, "near_me"),
            # Regular location (not near me)
            ("piano lessons in brooklyn", False, "borough"),  # Brooklyn is a borough
            ("piano lessons", False, None),
        ],
    )
    def test_near_me_detection(
        self,
        parser: QueryParser,
        query: str,
        expected_use_user_location: bool,
        expected_location_type: str | None,
    ) -> None:
        result = parser.parse(query)
        assert result.use_user_location == expected_use_user_location
        assert result.location_type == expected_location_type

    def test_near_me_stripped_from_service_query(self, parser: QueryParser) -> None:
        """Near me keywords should be stripped from service_query."""
        result = parser.parse("piano lessons near me")
        assert "near me" not in result.service_query.lower()
        assert "piano" in result.service_query.lower()

    def test_near_me_combined_with_other_constraints(
        self, parser: QueryParser
    ) -> None:
        """Near me should work with other constraints."""
        result = parser.parse("online piano lessons near me under 50")
        assert result.use_user_location is True
        assert result.location_type == "near_me"
        assert result.lesson_type == "online"
        assert result.max_price == 50
