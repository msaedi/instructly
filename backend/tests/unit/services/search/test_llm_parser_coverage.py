"""
Coverage tests for search/llm_parser.py targeting missed lines.

Targets:
  - L135-137: _parse_regex_sync
  - L193-195: CircuitOpenError handling
  - L214-219: _call_llm and _make_api_call branches
  - L355-356: _validate_time edge cases
"""

import asyncio
import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.search.llm_parser import LLMParser


def _make_llm_parser() -> LLMParser:
    """Create LLMParser with defaults."""
    parser = LLMParser.__new__(LLMParser)
    parser._user_id = None
    parser._region_code = "nyc"
    parser._client = None
    parser._client_max_retries = None
    return parser


@pytest.mark.unit
class TestLLMParserClient:
    """Cover client property branches."""

    def test_client_lazy_init(self):
        """L97-102: first access creates client."""
        parser = _make_llm_parser()
        with patch("app.services.search.llm_parser.get_search_config") as mock_config:
            mock_config.return_value = MagicMock(max_retries=2)
            client = parser.client
        assert client is not None

    def test_client_reinit_on_retries_change(self):
        """L103-108: max_retries changes -> recreates client."""
        parser = _make_llm_parser()
        with patch("app.services.search.llm_parser.get_search_config") as mock_config:
            mock_config.return_value = MagicMock(max_retries=2)
            client1 = parser.client
            mock_config.return_value = MagicMock(max_retries=5)
            client2 = parser.client
        assert client1 is not client2

    def test_client_max_retries_invalid(self):
        """L93-95: invalid max_retries -> defaults to 2."""
        parser = _make_llm_parser()
        with patch("app.services.search.llm_parser.get_search_config") as mock_config:
            mock_config.return_value = MagicMock(max_retries="invalid")
            client = parser.client
        assert client is not None


@pytest.mark.unit
class TestParseFallbacks:
    """Cover parse method fallback paths."""

    @pytest.mark.asyncio
    async def test_circuit_open_returns_regex(self):
        """L165-168: circuit is open -> returns regex result."""
        parser = _make_llm_parser()
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(
            service_query="piano", original_query="piano", parsing_mode="regex"
        )

        with patch("app.services.search.llm_parser.PARSING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = True
            result = await parser.parse("piano", regex_result=regex_result)
        assert result.parsing_mode == "regex"

    @pytest.mark.asyncio
    async def test_timeout_returns_regex(self):
        """L184-190: LLM times out -> returns regex result."""
        parser = _make_llm_parser()
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(
            service_query="piano", original_query="piano", parsing_mode="regex"
        )

        with patch("app.services.search.llm_parser.PARSING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = False
            with patch("app.services.search.llm_parser.get_search_config") as mock_config:
                mock_config.return_value = MagicMock(parsing_timeout_ms=100)
                with patch.object(parser, "_call_llm", side_effect=asyncio.TimeoutError()):
                    result = await parser.parse("piano", regex_result=regex_result)
        assert result.parsing_mode == "regex"

    @pytest.mark.asyncio
    async def test_circuit_open_error_during_call(self):
        """L192-195: CircuitOpenError during call -> returns regex."""
        parser = _make_llm_parser()
        from app.services.search.circuit_breaker import CircuitOpenError
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(
            service_query="piano", original_query="piano", parsing_mode="regex"
        )

        with patch("app.services.search.llm_parser.PARSING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = False
            with patch("app.services.search.llm_parser.get_search_config") as mock_config:
                mock_config.return_value = MagicMock(parsing_timeout_ms=5000)
                with patch.object(parser, "_call_llm", side_effect=CircuitOpenError()):
                    result = await parser.parse("piano", regex_result=regex_result)
        assert result.parsing_mode == "regex"

    @pytest.mark.asyncio
    async def test_openai_error_returns_regex(self):
        """L197-201: OpenAIError -> returns regex."""
        parser = _make_llm_parser()
        from openai import OpenAIError

        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(
            service_query="piano", original_query="piano", parsing_mode="regex"
        )

        with patch("app.services.search.llm_parser.PARSING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = False
            with patch("app.services.search.llm_parser.get_search_config") as mock_config:
                mock_config.return_value = MagicMock(parsing_timeout_ms=5000)
                with patch.object(parser, "_call_llm", side_effect=OpenAIError("API error")):
                    result = await parser.parse("piano", regex_result=regex_result)
        assert result.parsing_mode == "regex"

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_regex(self):
        """L203-206: unexpected error -> returns regex."""
        parser = _make_llm_parser()
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(
            service_query="piano", original_query="piano", parsing_mode="regex"
        )

        with patch("app.services.search.llm_parser.PARSING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = False
            with patch("app.services.search.llm_parser.get_search_config") as mock_config:
                mock_config.return_value = MagicMock(parsing_timeout_ms=5000)
                with patch.object(parser, "_call_llm", side_effect=RuntimeError("Unexpected")):
                    result = await parser.parse("piano", regex_result=regex_result)
        assert result.parsing_mode == "regex"


@pytest.mark.unit
class TestValidateTime:
    """Cover _validate_time edge cases."""

    def test_none_returns_none(self):
        parser = _make_llm_parser()
        assert parser._validate_time(None) is None

    def test_empty_string_returns_none(self):
        parser = _make_llm_parser()
        assert parser._validate_time("") is None

    def test_valid_time(self):
        parser = _make_llm_parser()
        assert parser._validate_time("14:30") == "14:30"

    def test_single_part_invalid(self):
        """L350-351: only one part -> None."""
        parser = _make_llm_parser()
        assert parser._validate_time("1430") is None

    def test_invalid_hour(self):
        parser = _make_llm_parser()
        assert parser._validate_time("25:00") is None

    def test_invalid_minute(self):
        parser = _make_llm_parser()
        assert parser._validate_time("14:61") is None

    def test_non_numeric_parts(self):
        """L355-356: ValueError on int conversion."""
        parser = _make_llm_parser()
        assert parser._validate_time("ab:cd") is None


@pytest.mark.unit
class TestMergeResults:
    """Cover _merge_results branches."""

    def test_merge_with_valid_llm_date(self):
        """L286-290: LLM provides valid date."""
        parser = _make_llm_parser()
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(service_query="piano", original_query="piano")
        llm_response = MagicMock()
        llm_response.service_query = "piano lessons"
        llm_response.max_price = 50
        llm_response.min_price = None
        llm_response.date = "2024-06-15"
        llm_response.date_range_start = None
        llm_response.date_range_end = None
        llm_response.time_after = "14:00"
        llm_response.time_before = "18:00"
        llm_response.location = "Brooklyn"
        llm_response.audience_hint = "kids"
        llm_response.skill_level = "beginner"
        llm_response.urgency = "high"
        llm_response.category_hint = "Music"
        llm_response.subcategory_hint = None
        llm_response.service_hint = "Piano"

        result = parser._merge_results(regex_result, llm_response, "piano")
        assert result.date == datetime.date(2024, 6, 15)
        assert result.date_type == "single"

    def test_merge_with_invalid_llm_date(self):
        """L291-293: LLM date is invalid format -> keeps regex date."""
        parser = _make_llm_parser()
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(
            service_query="piano",
            original_query="piano",
            date=datetime.date(2024, 7, 1),
            date_type="single",
        )
        llm_response = MagicMock()
        llm_response.service_query = "piano"
        llm_response.max_price = None
        llm_response.min_price = None
        llm_response.date = "not-a-date"
        llm_response.date_range_start = None
        llm_response.date_range_end = None
        llm_response.time_after = None
        llm_response.time_before = None
        llm_response.location = None
        llm_response.audience_hint = None
        llm_response.skill_level = None
        llm_response.urgency = None
        llm_response.category_hint = None
        llm_response.subcategory_hint = None
        llm_response.service_hint = None

        result = parser._merge_results(regex_result, llm_response, "piano")
        assert result.date == datetime.date(2024, 7, 1)

    def test_merge_with_date_range(self):
        """L299-307: LLM provides valid date range."""
        parser = _make_llm_parser()
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(service_query="piano", original_query="piano")
        llm_response = MagicMock()
        llm_response.service_query = "piano"
        llm_response.max_price = None
        llm_response.min_price = None
        llm_response.date = None
        llm_response.date_range_start = "2024-06-15"
        llm_response.date_range_end = "2024-06-20"
        llm_response.time_after = None
        llm_response.time_before = None
        llm_response.location = None
        llm_response.audience_hint = None
        llm_response.skill_level = None
        llm_response.urgency = None
        llm_response.category_hint = None
        llm_response.subcategory_hint = None
        llm_response.service_hint = None

        result = parser._merge_results(regex_result, llm_response, "piano")
        assert result.date_type == "range"
        assert result.date_range_start == datetime.date(2024, 6, 15)

    def test_merge_with_invalid_date_range(self):
        """L308-310: invalid LLM date range -> keeps regex."""
        parser = _make_llm_parser()
        from app.services.search.query_parser import ParsedQuery

        regex_result = ParsedQuery(service_query="piano", original_query="piano")
        llm_response = MagicMock()
        llm_response.service_query = "piano"
        llm_response.max_price = None
        llm_response.min_price = None
        llm_response.date = None
        llm_response.date_range_start = "invalid"
        llm_response.date_range_end = "invalid"
        llm_response.time_after = None
        llm_response.time_before = None
        llm_response.location = None
        llm_response.audience_hint = None
        llm_response.skill_level = None
        llm_response.urgency = None
        llm_response.category_hint = None
        llm_response.subcategory_hint = None
        llm_response.service_hint = None

        result = parser._merge_results(regex_result, llm_response, "piano")
        assert result.date_range_start is None
