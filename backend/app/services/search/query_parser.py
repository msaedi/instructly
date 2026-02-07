# backend/app/services/search/query_parser.py
"""
Regex fast-path parser for NL search queries.

Extracts structured constraints from natural language, leaving service query for semantic matching.
Handles 60-70% of queries without needing an LLM, providing sub-10ms parsing latency.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime
from datetime import timedelta
import re
import time
from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Tuple

import dateparser

from app.services.search.patterns import (
    ADULT_KEYWORDS,
    AGE_EXPLICIT,
    AGE_FOR_MY,
    AGE_YEAR_OLD,
    BUDGET_KEYWORDS,
    CATEGORY_KEYWORDS,
    KID_CONTEXT,
    KIDS_KEYWORDS,
    LESSON_TYPE_IN_PERSON,
    LESSON_TYPE_ONLINE,
    LOCATION_PREPOSITION,
    NEAR_ME,
    PREMIUM_KEYWORDS,
    PRICE_DOLLARS,
    PRICE_LESS_THAN,
    PRICE_MAX,
    PRICE_OR_LESS,
    PRICE_PER_HOUR,
    PRICE_UNDER_DOLLAR,
    PRICE_UNDER_IMPLICIT,
    SERVICE_KEYWORDS,
    SKILL_ADVANCED,
    SKILL_BEGINNER,
    SKILL_INTERMEDIATE,
    SUBCATEGORY_KEYWORDS,
    TEEN_KEYWORDS,
    TIME_AFTER,
    TIME_AFTERNOON,
    TIME_AROUND,
    TIME_AT,
    TIME_BEFORE,
    TIME_EVENING,
    TIME_MORNING,
    TIME_WINDOWS,
    URGENCY_HIGH,
    URGENCY_MEDIUM,
    WEEKDAY_PATTERN,
    WEEKDAYS,
    WEEKEND_PATTERN,
)
from app.services.search.typo_correction import correct_typos_cached

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Type alias for date to avoid shadowing in dataclass
DateType = datetime.date


# Lesson type enum for online/in-person filtering
LessonType = Literal["online", "in_person", "any"]

# Map proper taxonomy category names → price_threshold DB keys
_CATEGORY_TO_PRICE_KEY: Dict[str, str] = {
    "Music": "music",
    "Tutoring & Test Prep": "tutoring",
    "Sports & Fitness": "sports",
    "Dance": "sports",
    "Languages": "language",
    "Arts": "general",
    "Hobbies & Life Skills": "general",
}


@dataclass
class ParsedQuery:
    """Structured representation of a parsed natural language search query."""

    # Core query
    service_query: str  # "piano lessons" (constraints stripped)
    original_query: str  # Original user input preserved
    corrected_query: Optional[str] = None  # Typo-corrected query if different from original

    # Price constraints
    max_price: Optional[int] = None
    min_price: Optional[int] = None
    price_intent: Optional[Literal["budget", "standard", "premium"]] = None

    # Date constraints
    date: Optional[DateType] = None  # Single date
    date_range_start: Optional[DateType] = None  # Range start
    date_range_end: Optional[DateType] = None  # Range end
    date_type: Optional[Literal["single", "range", "weekend", "flexible"]] = None

    # Time constraints
    time_after: Optional[str] = None  # "17:00" (24hr format)
    time_before: Optional[str] = None  # "21:00"
    time_window: Optional[Literal["morning", "afternoon", "evening"]] = None

    # Location constraints
    location_text: Optional[str] = None  # Raw extracted text "brooklyn"
    location_type: Optional[Literal["borough", "neighborhood", "near_me"]] = None
    use_user_location: bool = False  # True when "near me" detected and user location should be used

    # Lesson type constraint (online vs in-person)
    lesson_type: LessonType = "any"  # "online", "in_person", or "any"

    # Audience hint (for ranking, NOT filtering)
    audience_hint: Optional[Literal["kids", "adults"]] = None
    skill_level: Optional[Literal["beginner", "intermediate", "advanced"]] = None

    # 3-level taxonomy hints (category → subcategory → service)
    category_hint: Optional[str] = None  # "Music", "Sports & Fitness", etc.
    subcategory_hint: Optional[str] = None  # "Martial Arts", "Test Prep", etc.
    service_hint: Optional[str] = None  # "Karate", "SAT Prep", etc.

    # Meta
    urgency: Optional[Literal["high", "medium", "low"]] = None
    parsing_mode: Literal["regex", "llm", "hybrid"] = "regex"
    parsing_latency_ms: int = 0
    confidence: float = 1.0  # 0.0 to 1.0
    needs_llm: bool = False  # Flag for complexity check


class QueryParser:
    """
    Fast-path regex parser for NL search queries.

    Supports multi-region architecture via region_code parameter.

    Usage:
        parser = QueryParser(db_session, user_id="user123", region_code="nyc")
        result = parser.parse("piano lessons under $50 tomorrow in brooklyn")
    """

    def __init__(
        self,
        db: "Session",
        user_id: Optional[str] = None,
        region_code: str = "nyc",
    ) -> None:
        self.db = db
        self._user_id = user_id
        self._region_code = region_code
        self._price_thresholds: Optional[Dict[Tuple[str, str], Dict[str, Optional[int]]]] = None

        # Initialize repositories (lazy import to avoid circular imports)
        from app.repositories.nl_search_repository import PriceThresholdRepository
        from app.services.search.location_resolver import LocationResolver

        self._price_threshold_repository = PriceThresholdRepository(db)
        self._location_resolver = LocationResolver(db, region_code=region_code)

    def _get_user_today(self) -> DateType:
        """
        Get today's date in user's timezone.

        Falls back to America/New_York if no user_id is provided.
        """
        if self._user_id:
            from app.core.timezone_utils import get_user_today_by_id

            return get_user_today_by_id(self._user_id, self.db)
        else:
            # Default to NYC timezone for anonymous searches
            import pytz

            nyc_tz = pytz.timezone("America/New_York")
            return datetime.datetime.now(nyc_tz).date()

    def parse(self, query: str) -> ParsedQuery:
        """
        Parse a natural language query into structured constraints.

        Returns ParsedQuery with needs_llm=True if query is too complex for regex.
        """
        start_time = time.perf_counter()

        original_query = query

        # Step 1: Apply typo correction
        corrected_text, was_corrected = correct_typos_cached(query)
        corrected_query = corrected_text if was_corrected else None

        # Use corrected query for parsing
        working_query = (corrected_text if was_corrected else query).lower().strip()
        extracted_spans: List[Tuple[int, int]] = []  # Track what we've extracted

        result = ParsedQuery(
            original_query=original_query,
            corrected_query=corrected_query,
            service_query="",  # Will be set at the end
            parsing_mode="regex",
        )

        # Apply extractors in order (price -> audience -> time -> lesson_type -> location -> skill -> urgency)
        working_query, result = self._extract_price(working_query, result, extracted_spans)
        working_query, result = self._extract_audience(working_query, result, extracted_spans)
        working_query, result = self._extract_time(working_query, result, extracted_spans)
        working_query, result = self._extract_date(working_query, result, extracted_spans)
        working_query, result = self._extract_lesson_type(working_query, result, extracted_spans)
        working_query, result = self._extract_location(working_query, result, extracted_spans)
        working_query, result = self._extract_skill_level(working_query, result, extracted_spans)
        working_query, result = self._extract_urgency(working_query, result, extracted_spans)

        # Resolve price intent to max_price if needed
        result = self._resolve_price_intent(result)

        # What remains is the service query
        result.service_query = self._clean_service_query(working_query)

        # Detect 3-level taxonomy hints (service → subcategory → category)
        result = self._detect_taxonomy(result)

        # Check if LLM is needed for complex queries
        result.needs_llm = self._check_complexity(result, working_query)
        result.confidence = 0.6 if result.needs_llm else 0.9

        # Record timing
        result.parsing_latency_ms = int((time.perf_counter() - start_time) * 1000)

        return result

    def _extract_price(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """Extract price constraints from query."""

        explicit_price_found = False

        # Try explicit $ patterns first (highest confidence)
        for pattern in [
            PRICE_UNDER_DOLLAR,
            PRICE_LESS_THAN,
            PRICE_MAX,
            PRICE_OR_LESS,
            PRICE_PER_HOUR,
        ]:
            match = pattern.search(query)
            if match:
                result.max_price = int(match.group(1))
                query = pattern.sub("", query)
                explicit_price_found = True
                break

        # Try "X dollars" pattern
        if not explicit_price_found:
            match = PRICE_DOLLARS.search(query)
            if match:
                result.max_price = int(match.group(1))
                query = PRICE_DOLLARS.sub("", query)
                explicit_price_found = True

        # Try implicit "under X" - BUT check for age disambiguation
        if not explicit_price_found:
            match = PRICE_UNDER_IMPLICIT.search(query)
            if match:
                number = int(match.group(1))
                # Check if this looks like an age, not a price
                if not self._is_age_context(query, match.start(), number):
                    if number >= 20:  # Numbers >= 20 are likely prices
                        result.max_price = number
                        query = PRICE_UNDER_IMPLICIT.sub("", query)
                        explicit_price_found = True

        # Always remove budget/premium intent words from service_query.
        # Only set price_intent when there is no explicit max_price.
        if BUDGET_KEYWORDS.search(query):
            if not explicit_price_found:
                result.price_intent = "budget"
            query = BUDGET_KEYWORDS.sub("", query)
        if PREMIUM_KEYWORDS.search(query):
            if not explicit_price_found:
                result.price_intent = "premium"
            query = PREMIUM_KEYWORDS.sub("", query)

        return query, result

    def _is_age_context(self, query: str, match_pos: int, number: int) -> bool:
        """
        Check if a number is in age context (not price context).

        Rules:
        - Number <= 18 AND kid/child/age keywords within 3 words -> age context
        - Number > 18 -> not age context (adults aren't described by age in searches)
        """
        if number > 18:
            return False

        # Get surrounding context (3 words before and after)
        words = query.split()
        # Find which word contains the match
        char_count = 0
        word_index = 0
        for i, word in enumerate(words):
            char_count += len(word) + 1  # +1 for space
            if char_count > match_pos:
                word_index = i
                break

        # Check 3 words before and after
        start = max(0, word_index - 3)
        end = min(len(words), word_index + 4)
        context = " ".join(words[start:end])

        return bool(KID_CONTEXT.search(context))

    def _extract_audience(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """Extract audience hint from query."""

        # Check for explicit age mentions -> kids
        for pattern in [AGE_YEAR_OLD, AGE_EXPLICIT, AGE_FOR_MY]:
            match = pattern.search(query)
            if match:
                age = int(match.group(1))
                if age <= 18:
                    result.audience_hint = "kids"
                else:
                    result.audience_hint = "adults"
                query = pattern.sub("", query)
                return query, result

        # Check for keyword hints
        if KIDS_KEYWORDS.search(query) or TEEN_KEYWORDS.search(query):
            result.audience_hint = "kids"
            query = KIDS_KEYWORDS.sub("", query)
            query = TEEN_KEYWORDS.sub("", query)
        elif ADULT_KEYWORDS.search(query):
            result.audience_hint = "adults"
            query = ADULT_KEYWORDS.sub("", query)

        return query, result

    def _extract_time(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """Extract time constraints from query."""

        def _add_minutes(time_str: str, delta_minutes: int) -> Optional[str]:
            """Add minutes to an HH:MM time string (clamped to same-day)."""
            try:
                hour_str, minute_str = time_str.split(":", 1)
                total = int(hour_str) * 60 + int(minute_str) + int(delta_minutes)
            except Exception:
                return None

            total = max(0, min(total, (24 * 60) - 1))
            return f"{total // 60:02d}:{total % 60:02d}"

        # Check for specific times
        for pattern, field_name in [
            (TIME_AFTER, "time_after"),
            (TIME_BEFORE, "time_before"),
            (TIME_AT, "time_at"),
            (TIME_AROUND, "time_around"),
        ]:
            match = pattern.search(query)
            if match:
                time_str = self._parse_time_match(match)
                if time_str:
                    if field_name == "time_at":
                        if not result.time_after:
                            result.time_after = time_str
                        # Specific times should be a narrow window, not open-ended.
                        if not result.time_before:
                            result.time_before = _add_minutes(time_str, 60)
                    elif field_name == "time_around":
                        # "around 2pm" -> +/- 1 hour window by default.
                        if not result.time_after:
                            result.time_after = _add_minutes(time_str, -60) or time_str
                        if not result.time_before:
                            result.time_before = _add_minutes(time_str, 60)
                    else:
                        setattr(result, field_name, time_str)
                    query = pattern.sub("", query)

        # Check for time windows
        time_window_patterns: List[
            Tuple[re.Pattern[str], Literal["morning", "afternoon", "evening"]]
        ] = [
            (TIME_MORNING, "morning"),
            (TIME_AFTERNOON, "afternoon"),
            (TIME_EVENING, "evening"),
        ]
        for pattern, window in time_window_patterns:
            if pattern.search(query):
                result.time_window = window
                start, end = TIME_WINDOWS[window]
                if not result.time_after:
                    result.time_after = start
                if not result.time_before:
                    result.time_before = end
                query = pattern.sub("", query)
                break

        return query, result

    def _parse_time_match(self, match: re.Match[str]) -> Optional[str]:
        """Convert regex time match to 24hr format string."""
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        meridiem = match.group(3).lower() if match.group(3) else None

        # Handle 12-hour to 24-hour conversion
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        elif meridiem is None and hour <= 6:
            # Assume PM for ambiguous times 1-6 without meridiem
            hour += 12

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
        return None

    def _extract_date(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """Extract date constraints using dateparser library."""

        # Check for "weekend" phrases ("weekend", "this weekend", "next weekend")
        weekend_match = WEEKEND_PATTERN.search(query)
        if weekend_match:
            prefix = (weekend_match.group(1) or "").strip().lower() or None

            # Calculate weekend dates using timezone-aware today
            today = self._get_user_today()
            days_until_saturday = (5 - today.weekday()) % 7
            if prefix == "next":
                days_until_saturday += 7
            saturday = today + timedelta(days=days_until_saturday)
            sunday = saturday + timedelta(days=1)

            result.date_type = "weekend"
            result.date = saturday  # For display/debug convenience
            result.date_range_start = saturday
            result.date_range_end = sunday

            query = (query[: weekend_match.start()] + " " + query[weekend_match.end() :]).strip()
            query = re.sub(r"\s+", " ", query)
            return query, result

        # Check for weekday names/abbreviations ("monday", "next fri", etc.)
        weekday_match = WEEKDAY_PATTERN.search(query)
        if weekday_match:
            prefix = (weekday_match.group(1) or "").strip().lower() or None
            weekday_label = (weekday_match.group(2) or "").strip().lower()

            # Disambiguation: "sat prep" means the SAT exam, not Saturday.
            if weekday_label == "sat":
                remainder = query[weekday_match.end() :].lstrip()
                next_word = remainder.split(" ", 1)[0].strip().lower() if remainder else ""
                if next_word in {"prep", "preparation", "test", "exam", "tutor", "tutoring"}:
                    weekday_match = None
            if weekday_match:
                target_weekday = WEEKDAYS.get(weekday_label)
                if target_weekday is not None:
                    today = self._get_user_today()
                    days_ahead = (target_weekday - today.weekday()) % 7
                    if prefix == "next":
                        days_ahead += 7

                    result.date = today + timedelta(days=days_ahead)
                    result.date_type = "single"

                    query = (
                        query[: weekday_match.start()] + " " + query[weekday_match.end() :]
                    ).strip()
                    query = re.sub(r"\s+", " ", query)
                    return query, result

        # Try dateparser for other date expressions
        date_patterns = [
            r"\b(today)\b",
            r"\b(tomorrow)\b",
            r"\b(next\s+week)\b",
            r"\b(in\s+\d+\s+days?)\b",
            r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",  # MM/DD or MM/DD/YYYY
            r"\b((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2})\b",
        ]

        for pattern_str in date_patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            match = pattern.search(query)
            if match:
                date_str = match.group(1)
                parsed = dateparser.parse(
                    date_str,
                    settings={
                        "TIMEZONE": "America/New_York",
                        "PREFER_DATES_FROM": "future",
                        "RETURN_AS_TIMEZONE_AWARE": False,
                    },
                )
                if parsed:
                    result.date = parsed.date()
                    result.date_type = "single"
                    query = pattern.sub("", query)
                    break

        return query, result

    def _extract_lesson_type(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """
        Extract lesson type (online vs in-person) from query.

        Online keywords: online, virtual, remote, zoom, video, webcam
        In-person keywords: in-person, face-to-face, in-home, at-home

        Note: Extract lesson type BEFORE location to avoid "in person" being
        parsed as a location ("in person" -> location "person").
        """
        # Check for in-person first (more specific pattern)
        if LESSON_TYPE_IN_PERSON.search(query):
            result.lesson_type = "in_person"
            query = LESSON_TYPE_IN_PERSON.sub("", query)
            return query, result

        # Check for online/virtual
        if LESSON_TYPE_ONLINE.search(query):
            result.lesson_type = "online"
            query = LESSON_TYPE_ONLINE.sub("", query)
            return query, result

        # Default is "any" (already set in dataclass)
        return query, result

    def _extract_location(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """Extract location constraints from query."""

        # Check for "near me" first
        if NEAR_ME.search(query):
            result.location_type = "near_me"
            result.use_user_location = True  # Signal that we need user's saved address
            query = NEAR_ME.sub("", query)
            return query, result

        # Check for "in/near/around <location>" pattern (supports multi-word locations)
        match = LOCATION_PREPOSITION.search(query)
        if match:
            location_text = " ".join(match.group(1).strip().lower().split())

            # Guard against common non-location phrases that match this regex.
            # Example: "in person" (lesson modality, not a neighborhood).
            if location_text in {"person", "in person", "online", "remote"}:
                return query, result

            result.location_text = location_text
            result.location_type = (
                "borough"
                if location_text
                in {
                    "manhattan",
                    "brooklyn",
                    "queens",
                    "bronx",
                    "staten island",
                    "bk",
                    "bklyn",
                    "bx",
                    "qns",
                    "si",
                }
                else "neighborhood"
            )
            query = LOCATION_PREPOSITION.sub("", query)
            return query, result

        # Direct borough/abbreviation match (without preposition)
        # Use word boundaries to avoid substring matches (e.g., "si" in "singing").
        query_lower = query.lower()
        for token in [
            "manhattan",
            "brooklyn",
            "queens",
            "bronx",
            "staten island",
            "bk",
            "bklyn",
            "bx",
            "qns",
            "si",
        ]:
            pattern = r"\b" + re.escape(token) + r"\b"
            if re.search(pattern, query_lower):
                result.location_text = token
                result.location_type = "borough"
                query = re.sub(pattern, "", query, flags=re.IGNORECASE)
                return query, result

        # Location suffix match without preposition (e.g., "violin lessons upper west side").
        # This is a best-effort heuristic validated via LocationResolver when possible.
        tokens = query_lower.split()
        if len(tokens) >= 3:
            location_hint_words = {
                "side",
                "village",
                "heights",
                "park",
                "hill",
                "district",
                "island",
                "harbor",
                "gardens",
                "garden",
            }
            direction_words = {
                "upper",
                "lower",
                "east",
                "west",
                "north",
                "south",
                "midtown",
                "downtown",
            }

            for n in [4, 3, 2]:
                if len(tokens) < n:
                    continue
                candidate = " ".join(tokens[-n:])
                if candidate in {"person", "online", "remote"}:
                    continue

                resolution = self._location_resolver.resolve_sync(candidate)
                looks_like_location = bool(
                    (set(candidate.split()) & location_hint_words)
                    or (set(candidate.split()) & direction_words)
                )
                if resolution.kind != "none" or looks_like_location:
                    result.location_text = candidate
                    result.location_type = (
                        "borough" if resolution.kind == "borough" else "neighborhood"
                    )
                    query = " ".join(tokens[:-n]).strip()
                    return query, result

            # Abbreviation suffix (single token), only for short alphabetic tokens.
            last = tokens[-1]
            if len(last) <= 5 and last.isalpha():
                resolution = self._location_resolver.resolve_sync(last)
                if resolution.kind != "none":
                    result.location_text = last
                    result.location_type = (
                        "borough" if resolution.kind == "borough" else "neighborhood"
                    )
                    query = " ".join(tokens[:-1]).strip()
                    return query, result

        return query, result

    def _extract_skill_level(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """Extract skill level from query."""

        if SKILL_BEGINNER.search(query):
            result.skill_level = "beginner"
            query = SKILL_BEGINNER.sub("", query)
        elif SKILL_INTERMEDIATE.search(query):
            result.skill_level = "intermediate"
            query = SKILL_INTERMEDIATE.sub("", query)
        elif SKILL_ADVANCED.search(query):
            result.skill_level = "advanced"
            query = SKILL_ADVANCED.sub("", query)

        return query, result

    def _extract_urgency(
        self, query: str, result: ParsedQuery, spans: List[Tuple[int, int]]
    ) -> Tuple[str, ParsedQuery]:
        """Extract urgency from query."""

        if URGENCY_HIGH.search(query):
            result.urgency = "high"
            query = URGENCY_HIGH.sub("", query)
        elif URGENCY_MEDIUM.search(query):
            result.urgency = "medium"
            query = URGENCY_MEDIUM.sub("", query)

        return query, result

    def _resolve_price_intent(self, result: ParsedQuery) -> ParsedQuery:
        """Convert price_intent to max_price/min_price based on detected category."""

        if result.max_price is not None or result.price_intent is None:
            return result  # Already have explicit price or no intent

        # Detect category from service query and normalise to price-threshold key
        raw_category = self._detect_category(result.service_query or result.original_query)
        category = _CATEGORY_TO_PRICE_KEY.get(raw_category, raw_category)

        # Load thresholds if needed
        if self._price_thresholds is None:
            self._load_price_thresholds()

        # Look up threshold
        if self._price_thresholds:
            key = (category, result.price_intent)
            threshold_info = self._price_thresholds.get(key)

            if threshold_info is None:
                # Fallback to general
                fallback_key = ("general", result.price_intent)
                threshold_info = self._price_thresholds.get(fallback_key)

            if threshold_info:
                # For budget/standard: use max_price
                # For premium: use min_price
                if result.price_intent == "premium":
                    result.min_price = threshold_info.get("min_price")
                else:
                    result.max_price = threshold_info.get("max_price")

        return result

    def _detect_category(self, query: str) -> str:
        """Detect service category from query text (for price intent resolution)."""
        query_lower = query.lower()
        # CATEGORY_KEYWORDS maps keyword→category_name; check longest keywords first
        for keyword in sorted(CATEGORY_KEYWORDS, key=len, reverse=True):
            if keyword in query_lower:
                return CATEGORY_KEYWORDS[keyword]
        return "general"

    def _detect_taxonomy(self, result: ParsedQuery) -> ParsedQuery:
        """Detect 3-level taxonomy hints from the service query.

        Resolution priority: service → subcategory → category (most specific wins).
        """
        text = (result.service_query or result.original_query).lower()

        # 1. Try SERVICE_KEYWORDS (most specific)
        for keyword in sorted(SERVICE_KEYWORDS, key=len, reverse=True):
            if keyword in text:
                result.service_hint = SERVICE_KEYWORDS[keyword]
                # Derive subcategory and category from service match
                if keyword in SUBCATEGORY_KEYWORDS:
                    result.subcategory_hint = SUBCATEGORY_KEYWORDS[keyword]
                if keyword in CATEGORY_KEYWORDS:
                    result.category_hint = CATEGORY_KEYWORDS[keyword]
                return result

        # 2. Try SUBCATEGORY_KEYWORDS
        for keyword in sorted(SUBCATEGORY_KEYWORDS, key=len, reverse=True):
            if keyword in text:
                result.subcategory_hint = SUBCATEGORY_KEYWORDS[keyword]
                if keyword in CATEGORY_KEYWORDS:
                    result.category_hint = CATEGORY_KEYWORDS[keyword]
                return result

        # 3. Try CATEGORY_KEYWORDS (broadest)
        for keyword in sorted(CATEGORY_KEYWORDS, key=len, reverse=True):
            if keyword in text:
                result.category_hint = CATEGORY_KEYWORDS[keyword]
                return result

        return result

    def _load_price_thresholds(self) -> None:
        """Load price thresholds for current region from database."""
        self._price_thresholds = self._price_threshold_repository.build_threshold_cache(
            region_code=self._region_code
        )

    def _clean_service_query(self, query: str) -> str:
        """Clean up remaining query text to get service query."""
        # Remove extra whitespace
        query = " ".join(query.split())

        # Remove leading/trailing punctuation and common words
        stopwords = {"for", "in", "the", "a", "an", "my", "me", "i", "want", "need", "looking"}
        words = query.split()
        words = [w for w in words if w.lower() not in stopwords and len(w) > 1]

        return " ".join(words).strip()

    def _check_complexity(self, result: ParsedQuery, remaining_query: str) -> bool:
        """
        Determine if query is too complex for regex and needs LLM.

        Returns True if LLM is needed.
        """
        # Get all words (including short ones for conditional checks)
        all_words = remaining_query.split()
        # Filter to meaningful words (> 2 chars) for word count
        words = [w for w in all_words if len(w) > 2]
        stopwords = {
            "for",
            "in",
            "the",
            "a",
            "an",
            "my",
            "me",
            "i",
            "want",
            "need",
            "looking",
            "and",
            "or",
        }
        meaningful_words = [w for w in words if w.lower() not in stopwords]

        # Rule 1: Too many remaining words
        if len(meaningful_words) > 6:
            return True

        # Rule 2: Contains conditional language (check ALL words including short ones)
        conditionals = {"or", "either", "if", "unless", "otherwise", "alternatively"}
        if any(word.lower() in conditionals for word in all_words):
            return True

        # Rule 3: Multiple service types mentioned
        service_indicators = {"and", "also", "plus", "as well"}
        if any(word.lower() in service_indicators for word in all_words):
            return True

        # Rule 4: References previous context
        context_refs = {"same", "again", "last time", "previous", "usual"}
        if any(ref in remaining_query.lower() for ref in context_refs):
            return True

        return False
