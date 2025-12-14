# backend/tests/unit/services/search/test_llm_parser.py
"""
Unit tests for LLM parser.
Uses mocks to avoid actual API calls.
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Dict, Tuple
from unittest.mock import AsyncMock, Mock, patch

import dateparser
import pytest

from app.services.search.circuit_breaker import (
    PARSING_CIRCUIT,
    CircuitState,
)
from app.services.search.config import get_search_config
from app.services.search.llm_parser import LLMParser, hybrid_parse
from app.services.search.llm_schema import LLMParsedQuery
from app.services.search.query_parser import ParsedQuery

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


def _build_location_cache() -> Dict[str, Dict[str, str]]:
    """Build mock location cache."""
    return {
        "brooklyn": {"name": "Brooklyn", "type": "borough", "borough": "Brooklyn"},
        "bk": {"name": "Brooklyn", "type": "borough", "borough": "Brooklyn"},
    }


def _build_threshold_cache() -> Dict[Tuple[str, str], Dict[str, int | None]]:
    """Build mock threshold cache with proper dict structure."""
    return {
        ("music", "budget"): {"max_price": 60, "min_price": None},
        ("general", "budget"): {"max_price": 50, "min_price": None},
    }


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
def llm_parser(mock_db: Mock) -> LLMParser:
    """Create LLMParser with mocked repositories."""
    with patch(
        "app.repositories.nl_search_repository.PriceThresholdRepository.build_threshold_cache"
    ) as mock_price:
        mock_price.return_value = _build_threshold_cache()
        parser = LLMParser(mock_db)
        # Pre-populate the cache to avoid repository calls
        parser._regex_parser._price_thresholds = _build_threshold_cache()
        # Mock _get_user_today to use date.today() for consistent timezone behavior
        parser._regex_parser._get_user_today = lambda: date.today()
        return parser


@pytest.fixture(autouse=True)
def reset_circuit() -> None:
    """Reset circuit breaker before each test."""
    PARSING_CIRCUIT.reset()
    yield
    PARSING_CIRCUIT.reset()


class TestLLMParser:
    """Tests for LLM parser functionality."""

    @pytest.mark.asyncio
    async def test_successful_parse(self, llm_parser: LLMParser) -> None:
        """Test successful LLM parsing."""
        mock_response = LLMParsedQuery(
            service_query="piano lessons",
            max_price=60,
            location="Brooklyn",
            audience_hint="kids",
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("cheap piano for my kid in brooklyn")

            assert result.service_query == "piano lessons"
            assert result.max_price == 60
            assert result.location_text == "Brooklyn"
            assert result.audience_hint == "kids"
            assert result.parsing_mode == "llm"

    @pytest.mark.asyncio
    async def test_timeout_fallback(self, llm_parser: LLMParser) -> None:
        """Test fallback to regex on timeout."""

        async def slow_call(*args: object, **kwargs: object) -> None:
            await asyncio.sleep(5)  # Longer than timeout

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = slow_call

            result = await llm_parser.parse("piano lessons in brooklyn")

            # Should fall back to regex
            assert result.parsing_mode == "regex"
            assert "piano" in result.service_query.lower()

    @pytest.mark.asyncio
    async def test_api_error_fallback(self, llm_parser: LLMParser) -> None:
        """Test fallback to regex on API error."""
        from openai import OpenAIError

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = OpenAIError("Rate limited")

            result = await llm_parser.parse("guitar lessons")

            assert result.parsing_mode == "regex"
            assert "guitar" in result.service_query.lower()

    @pytest.mark.asyncio
    async def test_circuit_breaker_open(self, llm_parser: LLMParser) -> None:
        """Test immediate fallback when circuit is open."""
        # Force circuit open
        for _ in range(10):
            PARSING_CIRCUIT._record_failure()

        assert PARSING_CIRCUIT.state == CircuitState.OPEN

        result = await llm_parser.parse("piano lessons")

        assert result.parsing_mode == "regex"

    @pytest.mark.asyncio
    async def test_typo_correction(self, llm_parser: LLMParser) -> None:
        """Test LLM corrects typos in service query."""
        mock_response = LLMParsedQuery(
            service_query="piano lessons",  # Corrected from "paino"
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("paino lesons")

            assert result.service_query == "piano lessons"

    @pytest.mark.asyncio
    async def test_date_parsing(self, llm_parser: LLMParser) -> None:
        """Test LLM parses relative dates."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        mock_response = LLMParsedQuery(
            service_query="math tutoring",
            date=tomorrow,
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("math tutor tomorrow")

            assert result.date == date.today() + timedelta(days=1)
            assert result.date_type == "single"

    @pytest.mark.asyncio
    async def test_invalid_date_uses_regex(self, llm_parser: LLMParser) -> None:
        """Test invalid LLM date falls back to regex result."""
        mock_response = LLMParsedQuery(
            service_query="piano lessons",
            date="not-a-date",  # Invalid format
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("piano tomorrow")

            # Should use regex-extracted date instead (tomorrow relative to now)
            assert result.date == date.today() + timedelta(days=1)

    @pytest.mark.asyncio
    async def test_time_validation(self, llm_parser: LLMParser) -> None:
        """Test time format validation."""
        mock_response = LLMParsedQuery(
            service_query="yoga class",
            time_after="17:00",
            time_before="25:00",  # Invalid
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("yoga after 5pm")

            assert result.time_after == "17:00"
            assert result.time_before is None  # Invalid time rejected


class TestHybridParse:
    """Tests for hybrid parsing function."""

    @pytest.mark.asyncio
    async def test_simple_query_skips_llm(self, mock_db: Mock) -> None:
        """Simple queries should not call LLM."""
        with patch(
            "app.services.search.llm_parser.LLMParser.parse",
            new_callable=AsyncMock,
        ) as mock_llm_parse:
            # Patch the regex parser to return a result that doesn't need LLM
            with patch("app.services.search.llm_parser.QueryParser") as mock_parser_class:
                mock_parser = Mock()
                mock_parser.parse.return_value = ParsedQuery(
                    original_query="piano lessons brooklyn",
                    service_query="piano lessons",
                    needs_llm=False,
                    parsing_mode="regex",
                )
                mock_parser_class.return_value = mock_parser

                result = await hybrid_parse("piano lessons brooklyn", mock_db)

                # LLM should not be called for simple queries
                assert result.parsing_mode == "regex"
                mock_llm_parse.assert_not_called()

    @pytest.mark.asyncio
    async def test_complex_query_uses_llm(self, mock_db: Mock) -> None:
        """Complex queries should use LLM."""
        # Patch the regex parser to return a result that needs LLM
        with patch("app.services.search.llm_parser.QueryParser") as mock_parser_class:
            mock_parser = Mock()
            mock_parser.parse.return_value = ParsedQuery(
                original_query="piano or guitar",
                service_query="piano or guitar",
                needs_llm=True,
                parsing_mode="regex",
            )
            mock_parser_class.return_value = mock_parser

            with patch(
                "app.services.search.llm_parser.LLMParser.parse",
                new_callable=AsyncMock,
            ) as mock_llm_parse:
                mock_llm_parse.return_value = ParsedQuery(
                    original_query="piano or guitar",
                    service_query="piano or guitar lessons",
                    parsing_mode="llm",
                )

                result = await hybrid_parse("piano or guitar lessons", mock_db)

                # LLM should have been called
                mock_llm_parse.assert_called_once()
                assert result.parsing_mode == "llm"


class TestCircuitBreaker:
    """Tests for circuit breaker behavior."""

    def test_circuit_opens_after_failures(self) -> None:
        """Circuit should open after threshold failures."""
        PARSING_CIRCUIT.reset()

        for _ in range(5):
            PARSING_CIRCUIT._record_failure()

        assert PARSING_CIRCUIT.state == CircuitState.OPEN

    def test_circuit_closes_on_success(self) -> None:
        """Circuit should close after successful test in half-open."""
        PARSING_CIRCUIT.reset()

        # Open the circuit
        for _ in range(5):
            PARSING_CIRCUIT._record_failure()

        # Simulate timeout passing
        PARSING_CIRCUIT._last_state_change = 0

        # Should transition to half-open on next check
        assert PARSING_CIRCUIT._should_attempt() is True
        assert PARSING_CIRCUIT.state == CircuitState.HALF_OPEN

        # Record success
        PARSING_CIRCUIT._record_success()

        assert PARSING_CIRCUIT.state == CircuitState.CLOSED

    def test_circuit_rejects_when_open(self) -> None:
        """Open circuit should reject attempts."""
        PARSING_CIRCUIT.reset()

        # Open the circuit
        for _ in range(5):
            PARSING_CIRCUIT._record_failure()

        assert PARSING_CIRCUIT._should_attempt() is False


class TestModelConfiguration:
    """Tests for model configuration."""

    def test_default_model(self) -> None:
        """Default model should be gpt-4o-mini when env var not set."""
        from app.services.search import config as config_module

        # Reset the singleton to test defaults
        with config_module._config_lock:
            original_config = config_module._config
            config_module._config = None

        try:
            # Clear relevant env vars for this test
            import os

            orig_env = os.environ.pop("OPENAI_PARSING_MODEL", None)
            try:
                config = get_search_config()
                assert "gpt-4o-mini" in config.parsing_model
            finally:
                if orig_env is not None:
                    os.environ["OPENAI_PARSING_MODEL"] = orig_env
        finally:
            # Restore original config
            with config_module._config_lock:
                config_module._config = original_config

    def test_schema_fields(self) -> None:
        """LLM schema should have all required fields."""
        schema = LLMParsedQuery.model_json_schema()

        required_fields = [
            "service_query",
            "max_price",
            "location",
            "audience_hint",
            "time_after",
            "time_before",
        ]

        for field in required_fields:
            assert field in schema["properties"]
