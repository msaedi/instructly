from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from openai import OpenAIError
import pytest

from app.services.search.location_llm_service import LocationLLMService


def _make_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _make_client(*, content: str | None = None, exc: Exception | None = None):
    async def _create(*args, **kwargs):
        if exc:
            raise exc
        return _make_response(content or "")

    client = SimpleNamespace()
    client.chat = SimpleNamespace()
    client.chat.completions = SimpleNamespace()
    client.chat.completions.create = AsyncMock(side_effect=_create)
    return client


def test_coerce_max_retries_defaults():
    service = LocationLLMService()
    assert service._coerce_max_retries("bad") == 2
    assert service._coerce_max_retries(-5) == 0


@pytest.mark.asyncio
async def test_resolve_empty_query_returns_none(monkeypatch):
    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="  ",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "empty_query"


@pytest.mark.asyncio
async def test_resolve_no_candidates_returns_none(monkeypatch):
    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="ues",
        allowed_region_names=[],
    )

    assert result is None
    assert debug["reason"] == "no_candidates"


@pytest.mark.asyncio
async def test_resolve_missing_api_key_returns_none(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="ues",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "missing_api_key"


@pytest.mark.asyncio
async def test_resolve_success_dedupes_and_canonicalizes(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(
        content='{"neighborhoods": ["Upper East Side", "upper east side", "Unknown"], "confidence": 1.1, "reason": "ok"}'
    )
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side", "SoHo"],
    )

    assert result is not None
    assert result["neighborhoods"] == ["Upper East Side"]
    assert result["confidence"] == 1.0
    assert debug["raw_response"]


@pytest.mark.asyncio
async def test_resolve_invalid_json_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(content="not json")
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] in {"invalid_json", "exception"}


@pytest.mark.asyncio
async def test_resolve_invalid_json_type_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(content="[]")
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "invalid_json"


@pytest.mark.asyncio
async def test_resolve_invalid_neighborhoods_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(content='{"neighborhoods": "UES", "confidence": 0.8}')
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "invalid_neighborhoods"


@pytest.mark.asyncio
async def test_resolve_no_valid_candidates_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(
        content='{"neighborhoods": ["Unknown"], "confidence": 0.9, "reason": "x"}'
    )
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "no_valid_candidates"


@pytest.mark.asyncio
async def test_resolve_empty_response_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(content="")
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "empty_response"


@pytest.mark.asyncio
async def test_resolve_confidence_coerces(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(
        content='{"neighborhoods": ["Upper East Side"], "confidence": "bad", "reason": "ok"}'
    )
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, _debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is not None
    assert result["confidence"] == 0.5


@pytest.mark.asyncio
async def test_resolve_timeout_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(exc=asyncio.TimeoutError())
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    with pytest.raises(asyncio.TimeoutError):
        await service.resolve(
            location_text="UES",
            allowed_region_names=["Upper East Side"],
        )


@pytest.mark.asyncio
async def test_resolve_openai_timeout_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(exc=OpenAIError("timed out"))
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "timeout"


@pytest.mark.asyncio
async def test_resolve_openai_error_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(exc=OpenAIError("bad request"))
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    result, debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
    )

    assert result is None
    assert debug["reason"] == "openai_error"


@pytest.mark.asyncio
async def test_resolve_openai_timeout_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    dummy = _make_client(exc=OpenAIError("timed out"))
    monkeypatch.setattr(
        "app.services.search.location_llm_service.AsyncOpenAI",
        lambda *args, **kwargs: dummy,
    )

    service = LocationLLMService()
    with pytest.raises(asyncio.TimeoutError):
        await service.resolve(
            location_text="UES",
            allowed_region_names=["Upper East Side"],
        )


@pytest.mark.asyncio
async def test_resolve_uses_longer_timeout_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    created = []

    def _factory(*_args, **kwargs):
        dummy = _make_client(
            content='{"neighborhoods": ["Upper East Side"], "confidence": 0.6, "reason": "ok"}'
        )
        created.append(kwargs)
        return dummy

    monkeypatch.setattr("app.services.search.location_llm_service.AsyncOpenAI", _factory)
    monkeypatch.setattr(
        "app.services.search.location_llm_service.get_search_config",
        lambda: SimpleNamespace(max_retries=1, location_timeout_ms=500),
    )

    service = LocationLLMService()
    result, _debug = await service.resolve_with_debug(
        location_text="UES",
        allowed_region_names=["Upper East Side"],
        timeout_s=1.5,
    )

    assert result is not None
    assert len(created) == 2


def test_client_recreates_when_timeout_changes(monkeypatch):
    created = []

    def _factory(*_args, **kwargs):
        created.append(kwargs)
        return _make_client(content='{"neighborhoods": ["Upper East Side"]}')

    monkeypatch.setattr("app.services.search.location_llm_service.AsyncOpenAI", _factory)
    monkeypatch.setattr(
        "app.services.search.location_llm_service.get_search_config",
        lambda: SimpleNamespace(max_retries=1, location_timeout_ms=500),
    )

    service = LocationLLMService()
    _ = service.client

    monkeypatch.setattr(
        "app.services.search.location_llm_service.get_search_config",
        lambda: SimpleNamespace(max_retries=1, location_timeout_ms=1500),
    )
    _ = service.client

    assert len(created) == 2
