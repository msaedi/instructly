"""
Coverage tests for search/location_llm_service.py targeting missed lines.

Targets:
  - L62-68: _coerce_max_retries invalid/negative
  - L75-93: client property lazy init and re-init on config change
  - L148-150: empty normalized query -> None
  - L152-154: no allowed_region_names -> None
  - L156-158: missing OPENAI_API_KEY -> None
  - L197-201: GPT-5 model -> max_completion_tokens
  - L216-218: empty response content -> None
  - L221-223: parsed is not dict -> None
  - L226-228: neighborhoods not a list -> None
  - L230-234: confidence non-numeric -> default 0.5
  - L241-242: non-string item in neighborhoods -> skipped
  - L244-246: item not in allowed list -> skipped
  - L247-248: duplicate canonical -> skipped
  - L254-256: no valid candidates -> None
  - L266-271: TimeoutError with raise_on_timeout
  - L272-283: OpenAIError handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_service():
    """Create LocationLLMService."""
    from app.services.search.location_llm_service import LocationLLMService

    return LocationLLMService()


@pytest.mark.unit
class TestCoerceMaxRetries:
    """Cover _coerce_max_retries edge cases."""

    def test_valid_int(self):
        from app.services.search.location_llm_service import LocationLLMService

        assert LocationLLMService._coerce_max_retries(3) == 3

    def test_string_convertible(self):
        from app.services.search.location_llm_service import LocationLLMService

        assert LocationLLMService._coerce_max_retries("5") == 5

    def test_invalid_value(self):
        """L66-67: invalid -> defaults to 2."""
        from app.services.search.location_llm_service import LocationLLMService

        assert LocationLLMService._coerce_max_retries("abc") == 2

    def test_none_value(self):
        from app.services.search.location_llm_service import LocationLLMService

        assert LocationLLMService._coerce_max_retries(None) == 2

    def test_negative_value(self):
        """L68: max(0, ...) -> 0."""
        from app.services.search.location_llm_service import LocationLLMService

        assert LocationLLMService._coerce_max_retries(-5) == 0


@pytest.mark.unit
class TestClientProperty:
    """Cover client property lazy init and config-change re-init."""

    def test_lazy_init(self):
        """L75-81: first access creates client."""
        svc = _make_service()
        assert svc._client is None

        mock_config = MagicMock()
        mock_config.max_retries = 2
        mock_config.location_timeout_ms = 3000

        with patch(
            "app.services.search.location_llm_service.get_search_config",
            return_value=mock_config,
        ):
            with patch("app.services.search.location_llm_service.AsyncOpenAI") as mock_openai:
                mock_openai.return_value = MagicMock()
                client = svc.client

        assert client is not None
        assert svc._client_max_retries == 2

    def test_reinit_on_max_retries_change(self):
        """L82-93: config change -> re-creates client."""
        svc = _make_service()
        svc._client = MagicMock()
        svc._client_max_retries = 2
        svc._client_timeout_s = 3.0

        mock_config = MagicMock()
        mock_config.max_retries = 5  # Changed
        mock_config.location_timeout_ms = 3000

        with patch(
            "app.services.search.location_llm_service.get_search_config",
            return_value=mock_config,
        ):
            with patch("app.services.search.location_llm_service.AsyncOpenAI") as mock_openai:
                new_client = MagicMock()
                mock_openai.return_value = new_client
                client = svc.client

        assert client is new_client
        assert svc._client_max_retries == 5


@pytest.mark.unit
class TestResolveInternal:
    """Cover _resolve_internal branches."""

    @pytest.mark.asyncio
    async def test_empty_query(self):
        """L148-150: empty query -> None."""
        svc = _make_service()
        result, debug = await svc._resolve_internal(
            location_text="   ",
            allowed_region_names=["Chelsea"],
        )
        assert result is None
        assert debug["reason"] == "empty_query"

    @pytest.mark.asyncio
    async def test_no_candidates(self):
        """L152-154: no allowed_region_names -> None."""
        svc = _make_service()
        result, debug = await svc._resolve_internal(
            location_text="museum mile",
            allowed_region_names=[],
        )
        assert result is None
        assert debug["reason"] == "no_candidates"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """L156-158: no OPENAI_API_KEY -> None."""
        svc = _make_service()
        with patch.dict("os.environ", {}, clear=True):
            with patch("os.getenv", return_value=None):
                result, debug = await svc._resolve_internal(
                    location_text="chelsea",
                    allowed_region_names=["Chelsea"],
                )
        assert result is None
        assert debug["reason"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_empty_response_content(self):
        """L216-218: empty response content -> None."""
        svc = _make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                        )

        assert result is None
        assert debug["reason"] == "empty_response"

    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        """L221-223: parsed is not dict -> None."""
        svc = _make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '"just a string"'

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                        )

        assert result is None
        assert debug["reason"] == "invalid_json"

    @pytest.mark.asyncio
    async def test_neighborhoods_not_list(self):
        """L226-228: neighborhoods not a list -> None."""
        import json

        svc = _make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"neighborhoods": "Chelsea", "confidence": 0.9}
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                        )

        assert result is None
        assert debug["reason"] == "invalid_neighborhoods"

    @pytest.mark.asyncio
    async def test_non_numeric_confidence(self):
        """L233-234: non-numeric confidence -> defaults to 0.5."""
        import json

        svc = _make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"neighborhoods": ["Chelsea"], "confidence": "high", "reason": "test"}
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                        )

        assert result is not None
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_non_string_item_skipped(self):
        """L241-242: non-string item in neighborhoods -> skipped."""
        import json

        svc = _make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"neighborhoods": [123, "Chelsea"], "confidence": 0.9, "reason": "test"}
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                        )

        assert result is not None
        assert result["neighborhoods"] == ["Chelsea"]

    @pytest.mark.asyncio
    async def test_item_not_in_allowed_list(self):
        """L244-246: item not in allowed list -> skipped."""
        import json

        svc = _make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"neighborhoods": ["Bogus Place"], "confidence": 0.9, "reason": "test"}
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="bogus",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                        )

        assert result is None
        assert debug["reason"] == "no_valid_candidates"

    @pytest.mark.asyncio
    async def test_timeout_raises_when_configured(self):
        """L266-270: TimeoutError with raise_on_timeout=True -> raises."""
        svc = _make_service()

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        with pytest.raises(asyncio.TimeoutError):
                            await svc._resolve_internal(
                                location_text="chelsea",
                                allowed_region_names=["Chelsea"],
                                timeout_s=0,
                                raise_on_timeout=True,
                            )

    @pytest.mark.asyncio
    async def test_timeout_returns_none_when_not_raising(self):
        """L266-271: TimeoutError with raise_on_timeout=False -> None."""
        svc = _make_service()

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                            raise_on_timeout=False,
                        )

        assert result is None
        assert debug["reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_openai_error_timed_out_raises(self):
        """L272-279: OpenAIError with 'timed out' + raise_on_timeout -> raises TimeoutError."""
        from openai import OpenAIError

        svc = _make_service()

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=OpenAIError("Request timed out")
        )

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        with pytest.raises(asyncio.TimeoutError):
                            await svc._resolve_internal(
                                location_text="chelsea",
                                allowed_region_names=["Chelsea"],
                                timeout_s=0,
                                raise_on_timeout=True,
                            )

    @pytest.mark.asyncio
    async def test_openai_error_non_timeout(self):
        """L280-283: OpenAIError without 'timed out' -> returns None."""
        from openai import OpenAIError

        svc = _make_service()

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=OpenAIError("Rate limit exceeded")
        )

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-4o-mini"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                            raise_on_timeout=True,
                        )

        assert result is None
        assert debug["reason"] == "openai_error"


@pytest.mark.unit
class TestGpt5ModelBranch:
    """Cover GPT-5 model request kwargs."""

    @pytest.mark.asyncio
    async def test_gpt5_uses_max_completion_tokens(self):
        """L197-201: gpt-5 model -> uses max_completion_tokens, no temperature."""
        import json

        svc = _make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"neighborhoods": ["Chelsea"], "confidence": 0.9, "reason": "test"}
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.location_timeout_ms = 3000
        mock_config.max_retries = 0

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "app.services.search.location_llm_service.get_search_config",
                return_value=mock_config,
            ):
                with patch(
                    "app.services.search.location_llm_service.settings"
                ) as mock_settings:
                    mock_settings.openai_location_model = "gpt-5-turbo"
                    svc._client = mock_client
                    svc._client_max_retries = 0
                    svc._client_timeout_s = 3.0

                    with patch(
                        "app.services.search.location_llm_service.OPENAI_CALL_SEMAPHORE",
                        new=asyncio.Semaphore(1),
                    ):
                        result, debug = await svc._resolve_internal(
                            location_text="chelsea",
                            allowed_region_names=["Chelsea"],
                            timeout_s=0,
                        )

        assert result is not None
        # Verify the request used max_completion_tokens
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "max_completion_tokens" in call_kwargs
        assert "temperature" not in call_kwargs
