from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.repositories.search_batch_repository import RegionInfo, RegionLookup
from app.schemas.nl_search import StageStatus
from app.services.search.location_resolver import ResolutionTier, ResolvedLocation
from app.services.search.nl_pipeline import location
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PipelineTimer,
    PreOpenAIData,
    UnresolvedLocationInfo,
)
from app.services.search.query_parser import ParsedQuery
from app.services.search.request_budget import RequestBudget


class DummySpan:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.attributes: dict[str, object] = {}
        self.error = error

    def set_attribute(self, key: str, value: object) -> None:
        if self.error is not None:
            raise self.error
        self.attributes[key] = value


def _patch_create_span(monkeypatch: pytest.MonkeyPatch) -> dict[str, DummySpan]:
    spans: dict[str, DummySpan] = {}

    @contextmanager
    def _create_span(name: str):
        span = spans.setdefault(name, DummySpan())
        yield span

    monkeypatch.setattr(location, "create_span", _create_span)
    return spans


def _patch_create_span_values(
    monkeypatch: pytest.MonkeyPatch,
    values: dict[str, DummySpan | None],
) -> None:
    @contextmanager
    def _create_span(name: str):
        yield values.get(name, DummySpan())

    monkeypatch.setattr(location, "create_span", _create_span)


def _make_region_lookup() -> RegionLookup:
    region = RegionInfo(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        display_name="Washington Heights",
        display_key="nyc-manhattan-washington-heights",
    )
    return RegionLookup(
        region_names=[region.region_name],
        by_name={region.region_name.lower(): region},
        by_id={region.region_id: region},
        embeddings=[],
        by_display_key={region.display_key or "": [region]},
    )


def _make_pre_data(
    parsed_query: ParsedQuery,
    *,
    location_resolution: ResolvedLocation | None = None,
    region_lookup: RegionLookup | None = None,
) -> PreOpenAIData:
    return PreOpenAIData(
        parsed_query=parsed_query,
        parse_latency_ms=1,
        text_results={},
        text_latency_ms=0,
        has_service_embeddings=True,
        best_text_score=0.0,
        require_text_match=False,
        skip_vector=False,
        region_lookup=region_lookup or _make_region_lookup(),
        location_resolution=location_resolution,
        location_normalized=None,
        cached_alias_normalized=None,
        fuzzy_score=None,
        location_llm_candidates=[],
    )


@pytest.mark.asyncio
async def test_resolve_location_llm_returns_none_for_empty_normalized_query() -> None:
    llm_service = SimpleNamespace(resolve=AsyncMock())

    result, llm_cache, unresolved = await location.resolve_location_llm(
        location_llm_service=llm_service,
        location_text=" ",
        original_query="",
        region_lookup=_make_region_lookup(),
        candidate_names=["Washington Heights"],
    )

    assert result is None
    assert llm_cache is None
    assert unresolved is None
    assert llm_service.resolve.await_count == 0


@pytest.mark.asyncio
async def test_resolve_location_llm_returns_unresolved_when_no_allowed_candidates() -> None:
    llm_service = SimpleNamespace(resolve=AsyncMock())

    result, llm_cache, unresolved = await location.resolve_location_llm(
        location_llm_service=llm_service,
        location_text="Washington",
        original_query="violin lessons in Washington",
        region_lookup=_make_region_lookup(),
        candidate_names=["", "  "],
    )

    assert result is None
    assert llm_cache is None
    assert unresolved == UnresolvedLocationInfo(
        normalized="washington",
        original_query="violin lessons in Washington",
    )
    assert llm_service.resolve.await_count == 0


@pytest.mark.asyncio
async def test_resolve_location_llm_passes_llm_response_to_parser() -> None:
    llm_service = SimpleNamespace(
        resolve=AsyncMock(return_value={"neighborhoods": ["Washington Heights"], "confidence": 0.9})
    )
    parsed_response = (
        ResolvedLocation.from_region(
            region_id="region-1",
            region_name="Washington Heights",
            borough="Manhattan",
            tier=ResolutionTier.LLM,
            confidence=0.9,
        ),
        LocationLLMCache(normalized="washington heights", confidence=0.9, region_ids=["region-1"]),
        None,
    )

    with patch.object(location, "parse_llm_location_response", return_value=parsed_response) as parser_mock:
        result = await location.resolve_location_llm(
            location_llm_service=llm_service,
            location_text="Washington Heights",
            original_query="violin lessons in Washington Heights",
            region_lookup=_make_region_lookup(),
            candidate_names=["Washington Heights"],
            timeout_s=0.25,
            normalized="washington heights",
        )

    llm_service.resolve.assert_awaited_once_with(
        location_text="violin lessons in Washington Heights",
        allowed_region_names=["Washington Heights"],
        timeout_s=0.25,
    )
    parser_mock.assert_called_once()
    assert result == parsed_response


@pytest.mark.asyncio
async def test_resolve_location_openai_mixed_case_tier4_sets_span_attrs_and_skips_tier5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _patch_create_span(monkeypatch)
    expected_result = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.EMBEDDING,
        confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE + 0.01,
    )

    async def _run_tier4(**kwargs):
        assert kwargs["normalized"] == "washington heights"
        return expected_result, ["Washington Heights", "Inwood"]

    monkeypatch.setattr(location, "run_tier4_embedding_search", _run_tier4)
    monkeypatch.setattr(
        location,
        "evaluate_tier5_budget",
        Mock(side_effect=AssertionError("Tier 5 budget path should not run")),
    )
    resolve_location_llm_fn = AsyncMock(
        side_effect=AssertionError("Tier 5 LLM path should not run")
    )

    resolved, llm_cache, unresolved = await location.resolve_location_openai(
        location_text="WaShInGtOn HeIgHtS",
        region_lookup=_make_region_lookup(),
        fuzzy_score=0.8,
        original_query="violin lessons in WaShInGtOn HeIgHtS",
        llm_candidates=None,
        allow_tier4=True,
        allow_tier5=True,
        location_embedding_service=Mock(),
        resolve_location_llm_fn=resolve_location_llm_fn,
        get_config=Mock(),
        logger=Mock(),
        tier4_high_confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=location.LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        llm_embedding_threshold=location.LOCATION_LLM_EMBEDDING_THRESHOLD,
    )

    assert resolved == expected_result
    assert llm_cache is None
    assert unresolved is None
    assert spans["search.location.tier4"].attributes == {
        "location.tier4.resolved": True,
        "location.tier4.confidence": expected_result.confidence,
        "location.tier4.candidate_count": 2,
    }
    assert resolve_location_llm_fn.await_count == 0


@pytest.mark.asyncio
async def test_resolve_location_openai_early_result_sets_setup_span_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _patch_create_span(monkeypatch)
    early_result = ResolvedLocation.from_borough(
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )
    monkeypatch.setattr(
        location,
        "setup_location_resolution",
        Mock(return_value=(None, early_result, None)),
    )
    monkeypatch.setattr(
        location,
        "run_tier4_embedding_search",
        AsyncMock(side_effect=AssertionError("Tier 4 should not run for early results")),
    )

    resolved, llm_cache, unresolved = await location.resolve_location_openai(
        location_text="Manhattan",
        region_lookup=_make_region_lookup(),
        fuzzy_score=None,
        original_query="violin lessons in Manhattan",
        llm_candidates=None,
        allow_tier4=True,
        allow_tier5=True,
        location_embedding_service=Mock(),
        resolve_location_llm_fn=AsyncMock(),
        get_config=Mock(),
        logger=Mock(),
        tier4_high_confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=location.LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        llm_embedding_threshold=location.LOCATION_LLM_EMBEDDING_THRESHOLD,
    )

    assert resolved == early_result
    assert llm_cache is None
    assert unresolved is None
    assert spans["search.location.setup"].attributes["location.resolved_tier"] == "tier1_3_early"


@pytest.mark.asyncio
async def test_resolve_location_openai_early_return_without_early_result_skips_setup_span_attr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _patch_create_span(monkeypatch)
    unresolved_info = UnresolvedLocationInfo(
        normalized="washington",
        original_query="violin lessons in Washington",
    )
    monkeypatch.setattr(
        location,
        "setup_location_resolution",
        Mock(return_value=(None, None, unresolved_info)),
    )

    resolved, llm_cache, unresolved = await location.resolve_location_openai(
        location_text="Washington",
        region_lookup=None,
        fuzzy_score=None,
        original_query="violin lessons in Washington",
        llm_candidates=None,
        allow_tier4=True,
        allow_tier5=True,
        location_embedding_service=Mock(),
        resolve_location_llm_fn=AsyncMock(),
        get_config=Mock(),
        logger=Mock(),
        tier4_high_confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=location.LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        llm_embedding_threshold=location.LOCATION_LLM_EMBEDDING_THRESHOLD,
    )

    assert resolved.not_found is True
    assert llm_cache is None
    assert unresolved == unresolved_info
    assert spans["search.location.setup"].attributes == {}


@pytest.mark.asyncio
async def test_resolve_location_openai_high_confidence_records_skip_and_consumes_existing_tier5_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_create_span(monkeypatch)
    expected_result = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.EMBEDDING,
        confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE + 0.01,
    )
    diagnostics = Mock()
    tier5_task = Mock()
    consume_mock = Mock()
    logger_mock = Mock()

    monkeypatch.setattr(
        location,
        "run_tier4_embedding_search",
        AsyncMock(return_value=(expected_result, [])),
    )
    monkeypatch.setattr(location, "consume_task_result", consume_mock)

    resolved, llm_cache, unresolved = await location.resolve_location_openai(
        location_text="Washington Heights",
        region_lookup=_make_region_lookup(),
        fuzzy_score=0.7,
        original_query="violin lessons in Washington Heights",
        llm_candidates=None,
        tier5_task=tier5_task,
        allow_tier4=True,
        allow_tier5=True,
        diagnostics=diagnostics,
        location_embedding_service=Mock(),
        resolve_location_llm_fn=AsyncMock(),
        get_config=Mock(),
        logger=logger_mock,
        tier4_high_confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=location.LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        llm_embedding_threshold=location.LOCATION_LLM_EMBEDDING_THRESHOLD,
    )

    assert resolved == expected_result
    assert llm_cache is None
    assert unresolved is None
    consume_mock.assert_called_once_with(tier5_task, label="location_llm", logger=logger_mock)
    diagnostics.record_location_tier.assert_called_once_with(
        tier=5,
        attempted=False,
        status=StageStatus.SKIPPED.value,
        duration_ms=0,
        details="tier4_high_confidence",
    )


@pytest.mark.asyncio
async def test_resolve_location_openai_unicode_live_miss_returns_unresolved_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_create_span(monkeypatch)
    unresolved_info = UnresolvedLocationInfo(
        normalized="wáshington",
        original_query="violin lessons in Wáshington",
    )
    monkeypatch.setattr(
        location,
        "run_tier4_embedding_search",
        AsyncMock(return_value=(None, [])),
    )
    monkeypatch.setattr(
        location,
        "await_tier5_result",
        AsyncMock(return_value=(None, None, unresolved_info)),
    )

    resolved, llm_cache, unresolved = await location.resolve_location_openai(
        location_text="Wáshington",
        region_lookup=_make_region_lookup(),
        fuzzy_score=0.0,
        original_query="violin lessons in Wáshington",
        llm_candidates=None,
        allow_tier4=True,
        allow_tier5=True,
        location_embedding_service=Mock(),
        resolve_location_llm_fn=AsyncMock(),
        get_config=Mock(),
        logger=Mock(),
        tier4_high_confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=location.LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        llm_embedding_threshold=location.LOCATION_LLM_EMBEDDING_THRESHOLD,
    )

    assert resolved.not_found is True
    assert llm_cache is None
    assert unresolved == unresolved_info
    assert unresolved.original_query == "violin lessons in Wáshington"


@pytest.mark.asyncio
async def test_resolve_location_openai_handles_missing_tier_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unresolved_info = UnresolvedLocationInfo(
        normalized="washington",
        original_query="violin lessons in Washington",
    )
    _patch_create_span_values(
        monkeypatch,
        {
            "search.location.setup": DummySpan(),
            "search.location.tier4": None,
            "search.location.tier5": None,
        },
    )
    monkeypatch.setattr(
        location,
        "run_tier4_embedding_search",
        AsyncMock(return_value=(None, [])),
    )
    monkeypatch.setattr(
        location,
        "await_tier5_result",
        AsyncMock(return_value=(None, None, unresolved_info)),
    )

    resolved, llm_cache, unresolved = await location.resolve_location_openai(
        location_text="Washington",
        region_lookup=_make_region_lookup(),
        fuzzy_score=0.1,
        original_query="violin lessons in Washington",
        llm_candidates=None,
        allow_tier4=True,
        allow_tier5=True,
        location_embedding_service=Mock(),
        resolve_location_llm_fn=AsyncMock(),
        get_config=Mock(),
        logger=Mock(),
        tier4_high_confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=location.LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        llm_embedding_threshold=location.LOCATION_LLM_EMBEDDING_THRESHOLD,
    )

    assert resolved.not_found is True
    assert llm_cache is None
    assert unresolved == unresolved_info


@pytest.mark.asyncio
async def test_resolve_location_openai_tier5_span_and_arbitration_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _patch_create_span(monkeypatch)
    tier4_result = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.EMBEDDING,
        confidence=0.4,
    )
    llm_result = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.LLM,
        confidence=0.9,
    )
    llm_cache = LocationLLMCache(
        normalized="washington heights",
        confidence=0.9,
        region_ids=["region-1"],
    )
    expected = (llm_result, llm_cache, None)
    logger_mock = Mock()

    monkeypatch.setattr(
        location,
        "run_tier4_embedding_search",
        AsyncMock(return_value=(tier4_result, ["Washington Heights"])),
    )
    monkeypatch.setattr(
        location,
        "evaluate_tier5_budget",
        Mock(return_value=(True, 0.25, None)),
    )
    monkeypatch.setattr(
        location,
        "await_tier5_result",
        AsyncMock(return_value=(llm_result, llm_cache, None)),
    )
    monkeypatch.setattr(
        location,
        "arbitrate_location_result",
        Mock(return_value=expected),
    )

    resolved, returned_cache, unresolved = await location.resolve_location_openai(
        location_text="Washington Heights",
        region_lookup=_make_region_lookup(),
        fuzzy_score=0.4,
        original_query="violin lessons in Washington Heights",
        llm_candidates=None,
        allow_tier4=True,
        allow_tier5=True,
        location_embedding_service=Mock(),
        resolve_location_llm_fn=AsyncMock(),
        get_config=Mock(),
        logger=logger_mock,
        tier4_high_confidence=location.LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=location.LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        llm_embedding_threshold=location.LOCATION_LLM_EMBEDDING_THRESHOLD,
    )

    assert resolved == llm_result
    assert returned_cache == llm_cache
    assert unresolved is None
    assert spans["search.location.tier5"].attributes["location.tier5.resolved"] is True


@pytest.mark.asyncio
async def test_resolve_location_llm_for_service_delegates_to_resolve_location_llm() -> None:
    service = SimpleNamespace(location_llm_service=Mock())
    expected = (
        ResolvedLocation.from_not_found(),
        None,
        UnresolvedLocationInfo(normalized="washington", original_query="violin lessons in Washington"),
    )

    with patch.object(location, "resolve_location_llm", AsyncMock(return_value=expected)) as resolve_mock:
        result = await location.resolve_location_llm_for_service(
            service,
            location_text="Washington",
            original_query="violin lessons in Washington",
            region_lookup=_make_region_lookup(),
            candidate_names=["Washington Heights"],
            timeout_s=0.5,
            normalized="washington",
        )

    assert result == expected
    resolve_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_location_openai_for_service_passes_service_dependencies() -> None:
    service = SimpleNamespace(location_embedding_service=Mock())
    expected = (
        ResolvedLocation.from_not_found(),
        None,
        UnresolvedLocationInfo(normalized="washington", original_query="violin lessons in Washington"),
    )

    with patch.object(location, "resolve_location_openai", AsyncMock(return_value=expected)) as resolve_mock:
        result = await location.resolve_location_openai_for_service(
            service,
            "Washington",
            region_lookup=_make_region_lookup(),
            fuzzy_score=0.0,
            original_query="violin lessons in Washington",
        )

    assert result == expected
    resolve_mock.assert_awaited_once()
    assert resolve_mock.await_args.kwargs["location_embedding_service"] is service.location_embedding_service


@pytest.mark.asyncio
async def test_resolve_location_stage_uses_cached_resolution_and_never_calls_live_resolver() -> None:
    cached_resolution = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )
    parsed_query = ParsedQuery(
        original_query="violin lessons in Washington Heights",
        service_query="violin lessons",
        location_text="Washington Heights",
        location_type="neighborhood",
    )
    pre_data = _make_pre_data(parsed_query, location_resolution=cached_resolution)
    timer = PipelineTimer()
    service = SimpleNamespace()

    with patch.object(
        location,
        "resolve_location_openai_for_service",
        AsyncMock(side_effect=AssertionError("Live location resolution should be skipped")),
    ):
        resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
            service,
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=None,
            budget=RequestBudget(total_ms=500),
            timer=timer,
            force_skip_tier5=False,
            force_skip_tier4=False,
            force_skip_embedding=False,
            tier5_task=None,
            tier5_started_at=None,
        )

    assert resolved == cached_resolution
    assert llm_cache is None
    assert unresolved is None
    assert timer.stages[-1]["name"] == "location_resolution"
    assert timer.stages[-1]["status"] == StageStatus.SUCCESS.value
    assert timer.stages[-1]["details"] == {"resolved": True, "tier": 1}


@pytest.mark.asyncio
async def test_resolve_location_stage_live_resolution_marks_budget_skips_and_handles_bad_tier_value() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons in Washington",
        service_query="violin lessons",
        location_text="Washington",
        location_type="neighborhood",
    )
    live_resolution = ResolvedLocation(tier=SimpleNamespace(value="bad"))
    pre_data = _make_pre_data(parsed_query, location_resolution=None)
    timer = PipelineTimer()
    budget = RequestBudget(total_ms=500)
    budget.can_afford_tier4 = Mock(return_value=False)
    budget.can_afford_tier5 = Mock(return_value=True)

    with patch.object(
        location,
        "resolve_location_openai_for_service",
        AsyncMock(return_value=(live_resolution, None, None)),
    ), patch("app.monitoring.otel.is_otel_enabled", return_value=False):
        resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
            SimpleNamespace(),
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=None,
            budget=budget,
            timer=timer,
            force_skip_tier5=True,
            force_skip_tier4=False,
            force_skip_embedding=False,
            tier5_task=None,
            tier5_started_at=None,
        )

    assert resolved == live_resolution
    assert llm_cache is None
    assert unresolved is None
    assert budget.skipped_operations == ["tier4_embedding", "tier5_llm"]
    assert timer.stages[-1]["status"] == StageStatus.MISS.value
    assert timer.stages[-1]["details"] == {"resolved": False, "tier": None}


@pytest.mark.asyncio
async def test_resolve_location_stage_defaults_to_not_found_when_live_resolution_returns_none() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons in Washington",
        service_query="violin lessons",
        location_text="Washington",
        location_type="neighborhood",
    )
    pre_data = _make_pre_data(parsed_query, location_resolution=None)
    timer = PipelineTimer()

    with patch.object(
        location,
        "resolve_location_openai_for_service",
        AsyncMock(return_value=(None, None, None)),
    ), patch("app.monitoring.otel.is_otel_enabled", return_value=False):
        resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
            SimpleNamespace(),
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=None,
            budget=RequestBudget(total_ms=500),
            timer=timer,
            force_skip_tier5=False,
            force_skip_tier4=False,
            force_skip_embedding=False,
            tier5_task=None,
            tier5_started_at=None,
        )

    assert resolved.not_found is True
    assert llm_cache is None
    assert unresolved is None
    assert timer.stages[-1]["status"] == StageStatus.MISS.value
    assert timer.stages[-1]["details"] == {"resolved": False, "tier": 0}


@pytest.mark.asyncio
async def test_resolve_location_stage_preserves_none_tier_without_parse_attempt() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons in Washington",
        service_query="violin lessons",
        location_text="Washington",
        location_type="neighborhood",
    )
    pre_data = _make_pre_data(parsed_query, location_resolution=None)
    timer = PipelineTimer()

    with patch.object(
        location,
        "resolve_location_openai_for_service",
        AsyncMock(return_value=(ResolvedLocation(), None, None)),
    ), patch("app.monitoring.otel.is_otel_enabled", return_value=False):
        resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
            SimpleNamespace(),
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=None,
            budget=RequestBudget(total_ms=500),
            timer=timer,
            force_skip_tier5=False,
            force_skip_tier4=False,
            force_skip_embedding=False,
            tier5_task=None,
            tier5_started_at=None,
        )

    assert resolved == ResolvedLocation()
    assert llm_cache is None
    assert unresolved is None
    assert timer.stages[-1]["details"] == {"resolved": False, "tier": None}


@pytest.mark.asyncio
async def test_resolve_location_stage_sets_current_span_resolved_tier_when_otel_enabled() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons in Washington Heights",
        service_query="violin lessons",
        location_text="Washington Heights",
        location_type="neighborhood",
    )
    cached_resolution = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )
    pre_data = _make_pre_data(parsed_query, location_resolution=cached_resolution)
    current_span = DummySpan()

    with patch("app.monitoring.otel.is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_current_span",
        return_value=current_span,
    ):
        resolved, _, _ = await location.resolve_location_stage_for_service(
            SimpleNamespace(),
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=None,
            budget=RequestBudget(total_ms=500),
            timer=PipelineTimer(),
            force_skip_tier5=False,
            force_skip_tier4=False,
            force_skip_embedding=False,
            tier5_task=None,
            tier5_started_at=None,
        )

    assert resolved == cached_resolution
    assert current_span.attributes["location.resolved_tier"] == "1"


@pytest.mark.asyncio
async def test_resolve_location_stage_logs_and_continues_when_span_attribute_write_fails() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons in Washington Heights",
        service_query="violin lessons",
        location_text="Washington Heights",
        location_type="neighborhood",
    )
    cached_resolution = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )
    pre_data = _make_pre_data(parsed_query, location_resolution=cached_resolution)
    timer = PipelineTimer()
    failing_span = DummySpan(error=RuntimeError("otel boom"))

    with patch("app.monitoring.otel.is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_current_span",
        return_value=failing_span,
    ), patch.object(location.logger, "debug") as debug_mock:
        resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
            SimpleNamespace(),
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=None,
            budget=RequestBudget(total_ms=500),
            timer=timer,
            force_skip_tier5=False,
            force_skip_tier4=False,
            force_skip_embedding=False,
            tier5_task=None,
            tier5_started_at=None,
        )

    assert resolved == cached_resolution
    assert llm_cache is None
    assert unresolved is None
    assert timer.stages[-1]["name"] == "location_resolution"
    assert timer.stages[-1]["status"] == StageStatus.SUCCESS.value
    debug_mock.assert_called_once_with(
        "Failed to set location.resolved_tier span attribute",
        exc_info=True,
    )


@pytest.mark.asyncio
async def test_resolve_location_stage_skips_timer_when_query_has_no_location() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons",
        service_query="violin lessons",
        location_text=None,
        location_type=None,
    )
    timer = PipelineTimer()

    resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
        SimpleNamespace(),
        parsed_query=parsed_query,
        pre_data=_make_pre_data(parsed_query, location_resolution=None),
        user_location=None,
        budget=RequestBudget(total_ms=500),
        timer=timer,
        force_skip_tier5=False,
        force_skip_tier4=False,
        force_skip_embedding=False,
        tier5_task=None,
        tier5_started_at=None,
    )

    assert resolved.not_found is True
    assert llm_cache is None
    assert unresolved is None
    assert timer.stages[-1] == {
        "name": "location_resolution",
        "duration_ms": 0,
        "status": StageStatus.SKIPPED.value,
        "details": {"reason": "no_location"},
    }


@pytest.mark.asyncio
async def test_resolve_location_stage_without_location_and_without_timer_returns_not_found() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons",
        service_query="violin lessons",
        location_text=None,
        location_type=None,
    )

    resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
        SimpleNamespace(),
        parsed_query=parsed_query,
        pre_data=_make_pre_data(parsed_query, location_resolution=None),
        user_location=None,
        budget=RequestBudget(total_ms=500),
        timer=None,
        force_skip_tier5=False,
        force_skip_tier4=False,
        force_skip_embedding=False,
        tier5_task=None,
        tier5_started_at=None,
    )

    assert resolved.not_found is True
    assert llm_cache is None
    assert unresolved is None


@pytest.mark.asyncio
async def test_resolve_location_stage_otel_with_no_current_span_returns_success() -> None:
    parsed_query = ParsedQuery(
        original_query="violin lessons in Washington Heights",
        service_query="violin lessons",
        location_text="Washington Heights",
        location_type="neighborhood",
    )
    cached_resolution = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Washington Heights",
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )

    with patch("app.monitoring.otel.is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_current_span",
        return_value=None,
    ):
        resolved, llm_cache, unresolved = await location.resolve_location_stage_for_service(
            SimpleNamespace(),
            parsed_query=parsed_query,
            pre_data=_make_pre_data(parsed_query, location_resolution=cached_resolution),
            user_location=None,
            budget=RequestBudget(total_ms=500),
            timer=PipelineTimer(),
            force_skip_tier5=False,
            force_skip_tier4=False,
            force_skip_embedding=False,
            tier5_task=None,
            tier5_started_at=None,
        )

    assert resolved == cached_resolution
    assert llm_cache is None
    assert unresolved is None
