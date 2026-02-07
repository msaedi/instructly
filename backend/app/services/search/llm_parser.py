# backend/app/services/search/llm_parser.py
"""
LLM parser for complex NL search queries.
Falls back to regex parser on any failure.
Uses strict timeouts to fail fast under load (no retries).
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
from typing import TYPE_CHECKING, Optional, cast

from openai import AsyncOpenAI, OpenAIError

from app.database import get_db_session
from app.services.search.circuit_breaker import (
    PARSING_CIRCUIT,
    CircuitOpenError,
)
from app.services.search.config import get_search_config
from app.services.search.llm_schema import LLMParsedQuery
from app.services.search.query_parser import ParsedQuery, QueryParser

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Strict OpenAI timeouts for async calls.
# Fail fast rather than block for 5+ seconds with retries.
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "2.0"))

# Legacy environment variable support (deprecated - use OPENAI_PARSING_MODEL)
# Configuration is now managed via app.services.search.config module

SYSTEM_PROMPT = """You are a search query parser for InstaInstru, a marketplace for lesson instructors in NYC.

Extract structured parameters from the user's search query.

Available fields:
- service_query: The type of lesson/service (e.g., "piano lessons", "math tutoring"). Correct obvious typos.
- max_price: Maximum price per hour in dollars (integer)
- min_price: Minimum price per hour in dollars (integer)
- date: Specific date in YYYY-MM-DD format
- date_range_start/end: Date range in YYYY-MM-DD format
- time_after: Earliest time in HH:MM format (24-hour)
- time_before: Latest time in HH:MM format (24-hour)
- location: NYC borough or neighborhood name
- audience_hint: "kids" if children/teens/age under 18 mentioned, "adults" if explicitly for adults
- skill_level: "beginner", "intermediate", or "advanced"
- urgency: "high" (urgent/asap), "medium" (soon), "low" (flexible)
- category_hint: One of "Tutoring & Test Prep", "Music", "Dance", "Languages", "Sports & Fitness", "Arts", "Hobbies & Life Skills", or null
- subcategory_hint: Specific subcategory within the category (e.g., "Martial Arts", "Test Prep", "Strings"), or null
- service_hint: Exact bookable service name (e.g., "Karate", "SAT Prep", "Piano"), or null

Today's date is {current_date}.

Rules:
- Only include fields explicitly or clearly implied in the query
- Correct obvious typos in service_query (e.g., "paino" → "piano")
- Convert relative dates to absolute (e.g., "tomorrow" → actual date)
- Convert times appropriately (e.g., "evening" → time_after: "17:00")
- "cheap"/"budget" → max_price based on category (music: 60, tutoring: 50, general: 50)
- audience_hint is for ranking boost only, NOT filtering
- Only set subcategory_hint if the query clearly targets a subcategory
- Only set service_hint if the query names a specific bookable service
"""


class LLMParser:
    """
    LLM parser for complex natural language queries.

    Usage:
        parser = LLMParser(db_session, user_id="user123")
        result = await parser.parse("piano or guitar lessons tomorrow")
    """

    def __init__(self, user_id: Optional[str] = None, region_code: str = "nyc") -> None:
        self._user_id = user_id
        self._region_code = region_code
        self._client: Optional[AsyncOpenAI] = None
        self._client_max_retries: Optional[int] = None

    @property
    def client(self) -> AsyncOpenAI:
        """Lazy initialization of OpenAI client with strict timeouts."""
        max_retries_raw = getattr(get_search_config(), "max_retries", 2)
        try:
            max_retries = int(max_retries_raw)
        except (TypeError, ValueError):
            max_retries = 2
        max_retries = max(0, max_retries)
        if self._client is None:
            self._client = AsyncOpenAI(
                timeout=OPENAI_TIMEOUT_S,
                max_retries=max_retries,
            )
            self._client_max_retries = max_retries
        elif self._client_max_retries is not None and self._client_max_retries != max_retries:
            self._client = AsyncOpenAI(
                timeout=OPENAI_TIMEOUT_S,
                max_retries=max_retries,
            )
            self._client_max_retries = max_retries
        return self._client

    async def _get_current_date(self) -> datetime.date:
        """
        Get current date in user's timezone for LLM context.

        Falls back to America/New_York if no user_id is provided.
        """
        user_id = self._user_id
        if user_id:
            from app.core.timezone_utils import get_user_today_by_id

            def _load_today() -> datetime.date:
                with get_db_session() as db:
                    return get_user_today_by_id(user_id, db)

            return await asyncio.to_thread(_load_today)
        else:
            # Default to NYC timezone for anonymous searches
            import pytz

            nyc_tz = pytz.timezone("America/New_York")
            return datetime.datetime.now(nyc_tz).date()

    @staticmethod
    def _parse_regex_sync(query: str, *, user_id: Optional[str], region_code: str) -> ParsedQuery:
        with get_db_session() as db:
            parser = QueryParser(db, user_id=user_id, region_code=region_code)
            return parser.parse(query)

    async def parse(self, query: str, regex_result: Optional[ParsedQuery] = None) -> ParsedQuery:
        """
        Parse a query using the configured OpenAI model with structured outputs.

        Args:
            query: The natural language query to parse
            regex_result: Optional pre-computed regex result (for hybrid mode)

        Returns:
            ParsedQuery with LLM-enhanced extraction

        Note:
            Falls back to regex_result on any failure (timeout, API error, circuit open)
        """
        start_time = time.perf_counter()

        # Get regex result as fallback
        if regex_result is None:
            regex_result = await asyncio.to_thread(
                self._parse_regex_sync,
                query,
                user_id=self._user_id,
                region_code=self._region_code,
            )

        # Check circuit breaker
        if PARSING_CIRCUIT.is_open:
            logger.info("LLM parsing circuit is OPEN, using regex fallback")
            regex_result.parsing_mode = "regex"
            return regex_result

        try:
            # Call LLM with configurable timeout
            config = get_search_config()
            timeout_seconds = config.parsing_timeout_ms / 1000.0
            llm_response = await asyncio.wait_for(self._call_llm(query), timeout=timeout_seconds)

            # Merge LLM result with regex result
            result = self._merge_results(regex_result, llm_response, query)
            result.parsing_mode = "llm"
            result.parsing_latency_ms = int((time.perf_counter() - start_time) * 1000)
            result.confidence = 0.95

            return result

        except asyncio.TimeoutError:
            # Don't record_failure here - the inner CircuitBreaker.call() handles it
            # when the task is cancelled
            logger.warning(f"LLM parsing timed out after {timeout_seconds:.1f}s")
            regex_result.parsing_mode = "regex"
            regex_result.parsing_latency_ms = int((time.perf_counter() - start_time) * 1000)
            return regex_result

        except CircuitOpenError:
            logger.info("LLM parsing circuit opened during call")
            regex_result.parsing_mode = "regex"
            return regex_result

        except OpenAIError as e:
            # Don't record_failure here - CircuitBreaker.call() already did
            logger.warning(f"OpenAI API error: {e}")
            regex_result.parsing_mode = "regex"
            return regex_result

        except Exception as e:
            logger.error(f"Unexpected LLM parsing error: {e}")
            regex_result.parsing_mode = "regex"
            return regex_result

    async def _call_llm(self, query: str) -> LLMParsedQuery:
        """
        Call the configured OpenAI parsing model with structured output parsing.

        Uses OpenAI's beta.chat.completions.parse() for reliable JSON extraction.
        """
        current_date = (await self._get_current_date()).isoformat()
        system_prompt = SYSTEM_PROMPT.format(current_date=current_date)

        response = await PARSING_CIRCUIT.call(self._make_api_call, query, system_prompt)

        return response

    async def _make_api_call(self, query: str, system_prompt: str) -> LLMParsedQuery:
        """Make the actual API call to OpenAI."""
        config = get_search_config()
        # GPT-5 models require `max_completion_tokens` (not `max_tokens`).
        # Older models (e.g., gpt-4o-mini) use `max_tokens`.
        model = config.parsing_model
        request_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "response_format": LLMParsedQuery,
        }
        # Note: GPT-5 models currently only support default temperature; passing 0 triggers 400s.
        if not str(model).startswith("gpt-5"):
            request_kwargs["temperature"] = 0  # Deterministic output where supported
        if str(model).startswith("gpt-5"):
            request_kwargs["max_completion_tokens"] = 500
        else:
            request_kwargs["max_tokens"] = 500

        response = await self.client.beta.chat.completions.parse(**request_kwargs)

        message = response.choices[0].message

        # Check for refusal
        if message.refusal:
            logger.warning(f"LLM refused to parse: {message.refusal}")
            raise ValueError(f"LLM refusal: {message.refusal}")

        # Return typed result
        if message.parsed is None:
            raise ValueError("LLM returned no parsed content")
        # OpenAI's parse() method with response_format returns the schema type
        # The type is guaranteed by the response_format parameter
        return cast(LLMParsedQuery, message.parsed)

    def _merge_results(
        self,
        regex_result: ParsedQuery,
        llm_response: LLMParsedQuery,
        original_query: str,
    ) -> ParsedQuery:
        """
        Merge LLM result with regex result.

        Strategy:
        - LLM service_query takes priority (has typo correction)
        - For other fields, prefer LLM if present, else keep regex
        - Validate LLM values before using
        """
        result = ParsedQuery(
            original_query=original_query,
            corrected_query=regex_result.corrected_query,
            service_query=llm_response.service_query or regex_result.service_query,
            parsing_mode="llm",
        )

        # Price - prefer LLM (may have resolved intent)
        result.max_price = llm_response.max_price or regex_result.max_price
        result.min_price = llm_response.min_price or regex_result.min_price
        result.price_intent = regex_result.price_intent  # Keep regex intent for debugging

        # Date - validate LLM date format
        if llm_response.date:
            try:
                parsed_date = datetime.datetime.strptime(llm_response.date, "%Y-%m-%d").date()
                result.date = parsed_date
                result.date_type = "single"
            except ValueError:
                result.date = regex_result.date
                result.date_type = regex_result.date_type
        else:
            result.date = regex_result.date
            result.date_type = regex_result.date_type

        # Date range
        if llm_response.date_range_start and llm_response.date_range_end:
            try:
                result.date_range_start = datetime.datetime.strptime(
                    llm_response.date_range_start, "%Y-%m-%d"
                ).date()
                result.date_range_end = datetime.datetime.strptime(
                    llm_response.date_range_end, "%Y-%m-%d"
                ).date()
                result.date_type = "range"
            except ValueError:
                result.date_range_start = regex_result.date_range_start
                result.date_range_end = regex_result.date_range_end
        else:
            result.date_range_start = regex_result.date_range_start
            result.date_range_end = regex_result.date_range_end

        # Time - validate format
        result.time_after = self._validate_time(llm_response.time_after) or regex_result.time_after
        result.time_before = (
            self._validate_time(llm_response.time_before) or regex_result.time_before
        )
        result.time_window = regex_result.time_window  # Keep regex time window

        # Location - prefer LLM (may normalize)
        result.location_text = llm_response.location or regex_result.location_text
        result.location_type = regex_result.location_type  # Keep regex type detection

        # Audience and skill - prefer LLM
        result.audience_hint = llm_response.audience_hint or regex_result.audience_hint
        result.skill_level = llm_response.skill_level or regex_result.skill_level

        # Urgency
        result.urgency = llm_response.urgency or regex_result.urgency

        # 3-level taxonomy hints — prefer LLM, fall back to regex
        result.category_hint = llm_response.category_hint or regex_result.category_hint
        result.subcategory_hint = llm_response.subcategory_hint or regex_result.subcategory_hint
        result.service_hint = llm_response.service_hint or regex_result.service_hint

        # Complexity flag (LLM handled it, so not needed)
        result.needs_llm = False

        return result

    def _validate_time(self, time_str: Optional[str]) -> Optional[str]:
        """Validate time string is in HH:MM format."""
        if not time_str:
            return None

        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                return None
            hour, minute = int(parts[0]), int(parts[1])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"
        except (ValueError, AttributeError):
            pass

        return None


async def hybrid_parse(
    query: str,
    user_id: Optional[str] = None,
    region_code: str = "nyc",
) -> ParsedQuery:
    """
    Parse a query using regex first, then LLM if needed.

    This is the main entry point for the parsing pipeline.

    Args:
        query: The natural language query to parse
        db: Database session
        user_id: Optional user ID for timezone-aware date handling
        region_code: Region for location/price lookups (default: nyc)

    Returns:
        ParsedQuery with extracted constraints
    """

    def _parse_regex() -> ParsedQuery:
        with get_db_session() as db:
            parser = QueryParser(db, user_id=user_id, region_code=region_code)
            return parser.parse(query)

    regex_result = await asyncio.to_thread(_parse_regex)

    # If regex handled it well, return immediately
    if not regex_result.needs_llm:
        return regex_result

    # Otherwise, enhance with LLM
    llm_parser = LLMParser(user_id=user_id, region_code=region_code)
    return await llm_parser.parse(query, regex_result)
