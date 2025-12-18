# backend/tests/unit/services/search/test_llm_parser.py
"""
Unit tests for LLM parser.
Uses mocks to avoid actual API calls.
"""
import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.search.circuit_breaker import (
    PARSING_CIRCUIT,
    CircuitState,
)
from app.services.search.config import get_search_config
from app.services.search.llm_parser import LLMParser, hybrid_parse
from app.services.search.llm_schema import LLMParsedQuery
from app.services.search.query_parser import ParsedQuery


@pytest.fixture
def llm_parser() -> LLMParser:
    """Create LLMParser with no DB access (regex fallback injected per-test)."""
    return LLMParser()


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
        regex_result = ParsedQuery(
            original_query="cheap piano for my kid in brooklyn",
            service_query="piano lessons",
            location_text="brooklyn",
            parsing_mode="regex",
        )
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

            result = await llm_parser.parse(
                "cheap piano for my kid in brooklyn", regex_result=regex_result
            )

            assert result.service_query == "piano lessons"
            assert result.max_price == 60
            assert result.location_text == "Brooklyn"
            assert result.audience_hint == "kids"
            assert result.parsing_mode == "llm"

    @pytest.mark.asyncio
    async def test_timeout_fallback(self, llm_parser: LLMParser) -> None:
        """Test fallback to regex on timeout."""
        regex_result = ParsedQuery(
            original_query="piano lessons in brooklyn",
            service_query="piano lessons",
            location_text="brooklyn",
            parsing_mode="regex",
        )

        async def slow_call(*args: object, **kwargs: object) -> None:
            await asyncio.sleep(5)  # Longer than timeout

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = slow_call

            result = await llm_parser.parse(
                "piano lessons in brooklyn", regex_result=regex_result
            )

            # Should fall back to regex
            assert result.parsing_mode == "regex"
            assert "piano" in result.service_query.lower()

    @pytest.mark.asyncio
    async def test_api_error_fallback(self, llm_parser: LLMParser) -> None:
        """Test fallback to regex on API error."""
        from openai import OpenAIError

        regex_result = ParsedQuery(
            original_query="guitar lessons",
            service_query="guitar lessons",
            parsing_mode="regex",
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = OpenAIError("Rate limited")

            result = await llm_parser.parse("guitar lessons", regex_result=regex_result)

            assert result.parsing_mode == "regex"
            assert "guitar" in result.service_query.lower()

    @pytest.mark.asyncio
    async def test_circuit_breaker_open(self, llm_parser: LLMParser) -> None:
        """Test immediate fallback when circuit is open."""
        # Force circuit open
        for _ in range(10):
            PARSING_CIRCUIT._record_failure()

        assert PARSING_CIRCUIT.state == CircuitState.OPEN

        regex_result = ParsedQuery(
            original_query="piano lessons",
            service_query="piano lessons",
            parsing_mode="regex",
        )
        result = await llm_parser.parse("piano lessons", regex_result=regex_result)

        assert result.parsing_mode == "regex"

    @pytest.mark.asyncio
    async def test_typo_correction(self, llm_parser: LLMParser) -> None:
        """Test LLM corrects typos in service query."""
        regex_result = ParsedQuery(
            original_query="paino lesons",
            service_query="paino lesons",
            parsing_mode="regex",
        )
        mock_response = LLMParsedQuery(
            service_query="piano lessons",  # Corrected from "paino"
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("paino lesons", regex_result=regex_result)

            assert result.service_query == "piano lessons"

    @pytest.mark.asyncio
    async def test_date_parsing(self, llm_parser: LLMParser) -> None:
        """Test LLM parses relative dates."""
        regex_result = ParsedQuery(
            original_query="math tutor tomorrow",
            service_query="math tutoring",
            parsing_mode="regex",
        )
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        mock_response = LLMParsedQuery(
            service_query="math tutoring",
            date=tomorrow,
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("math tutor tomorrow", regex_result=regex_result)

            assert result.date == date.today() + timedelta(days=1)
            assert result.date_type == "single"

    @pytest.mark.asyncio
    async def test_invalid_date_uses_regex(self, llm_parser: LLMParser) -> None:
        """Test invalid LLM date falls back to regex result."""
        regex_result = ParsedQuery(
            original_query="piano tomorrow",
            service_query="piano lessons",
            parsing_mode="regex",
            date=date.today() + timedelta(days=1),
            date_type="single",
        )
        mock_response = LLMParsedQuery(
            service_query="piano lessons",
            date="not-a-date",  # Invalid format
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("piano tomorrow", regex_result=regex_result)

            # Should use regex-extracted date instead (tomorrow relative to now)
            assert result.date == date.today() + timedelta(days=1)

    @pytest.mark.asyncio
    async def test_time_validation(self, llm_parser: LLMParser) -> None:
        """Test time format validation."""
        regex_result = ParsedQuery(
            original_query="yoga after 5pm",
            service_query="yoga class",
            parsing_mode="regex",
        )
        mock_response = LLMParsedQuery(
            service_query="yoga class",
            time_after="17:00",
            time_before="25:00",  # Invalid
        )

        with patch.object(
            llm_parser, "_call_llm", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            result = await llm_parser.parse("yoga after 5pm", regex_result=regex_result)

            assert result.time_after == "17:00"
            assert result.time_before is None  # Invalid time rejected

    @pytest.mark.asyncio
    async def test_make_api_call_uses_max_completion_tokens_for_gpt5(
        self, llm_parser: LLMParser
    ) -> None:
        """GPT-5 models require max_completion_tokens (not max_tokens)."""
        mock_response = LLMParsedQuery(service_query="piano lessons")
        message = Mock(parsed=mock_response, refusal=None)
        response = Mock(choices=[Mock(message=message)])

        parse_mock = AsyncMock(return_value=response)
        llm_parser._client = Mock(
            beta=Mock(chat=Mock(completions=Mock(parse=parse_mock)))  # type: ignore[arg-type]
        )

        with patch("app.services.search.llm_parser.get_search_config") as mock_config:
            mock_config.return_value = Mock(parsing_model="gpt-5-nano")
            result = await llm_parser._make_api_call("piano", "sys")

        assert result.service_query == "piano lessons"
        _, kwargs = parse_mock.call_args
        assert kwargs.get("max_completion_tokens") == 500
        assert "max_tokens" not in kwargs
        assert "temperature" not in kwargs

    @pytest.mark.asyncio
    async def test_make_api_call_uses_max_tokens_for_non_gpt5(
        self, llm_parser: LLMParser
    ) -> None:
        """Older models should keep using max_tokens."""
        mock_response = LLMParsedQuery(service_query="piano lessons")
        message = Mock(parsed=mock_response, refusal=None)
        response = Mock(choices=[Mock(message=message)])

        parse_mock = AsyncMock(return_value=response)
        llm_parser._client = Mock(
            beta=Mock(chat=Mock(completions=Mock(parse=parse_mock)))  # type: ignore[arg-type]
        )

        with patch("app.services.search.llm_parser.get_search_config") as mock_config:
            mock_config.return_value = Mock(parsing_model="gpt-4o-mini")
            result = await llm_parser._make_api_call("piano", "sys")

        assert result.service_query == "piano lessons"
        _, kwargs = parse_mock.call_args
        assert kwargs.get("max_tokens") == 500
        assert "max_completion_tokens" not in kwargs
        assert kwargs.get("temperature") == 0


class TestHybridParse:
    """Tests for hybrid parsing function."""

    @pytest.mark.asyncio
    async def test_simple_query_skips_llm(self) -> None:
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
                session_ctx = Mock()
                session_ctx.__enter__ = Mock(return_value=Mock())
                session_ctx.__exit__ = Mock(return_value=None)

                with patch(
                    "app.services.search.llm_parser.get_db_session",
                    return_value=session_ctx,
                ):
                    result = await hybrid_parse("piano lessons brooklyn")

                # LLM should not be called for simple queries
                assert result.parsing_mode == "regex"
                mock_llm_parse.assert_not_called()

    @pytest.mark.asyncio
    async def test_complex_query_uses_llm(self) -> None:
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
                session_ctx = Mock()
                session_ctx.__enter__ = Mock(return_value=Mock())
                session_ctx.__exit__ = Mock(return_value=None)

                with patch(
                    "app.services.search.llm_parser.get_db_session",
                    return_value=session_ctx,
                ):
                    result = await hybrid_parse("piano or guitar lessons")

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
        """Default model should be gpt-5-nano when env var not set."""
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
                assert "gpt-5-nano" in config.parsing_model
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
