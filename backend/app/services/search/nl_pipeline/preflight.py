"""Service-facing preflight orchestration helpers."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app import database as database_module
from app.repositories import search_batch_repository as search_batch_repository_module
from app.schemas.nl_search import StageStatus
from app.services.search import (
    config as config_module,
    query_parser as query_parser_module,
    retriever as retriever_module,
)
from app.services.search.nl_pipeline import location, location_helpers, runtime
from app.services.search.nl_pipeline.models import PreOpenAIData
from app.services.search.nl_pipeline.preflight_core import (
    build_cache_filters,
    coerce_skill_level_override,
    compute_text_match_flags,
    embed_query_with_timeout,
    normalize_filter_values,
    normalize_taxonomy_filter_selections,
    prepare_search_filters,
    run_pre_openai_burst,
)
from app.services.search.nl_pipeline.preflight_parse import (
    _cache_parsed_query_safe,
    _run_llm_parse_for_service,
    parse_query,
)
from app.services.search.nl_pipeline.protocols import SearchServiceLike
from app.services.search.request_budget import RequestBudget

if TYPE_CHECKING:
    from app.services.search.nl_pipeline.models import PipelineTimer, SearchMetrics
    from app.services.search.query_parser import ParsedQuery

logger = logging.getLogger(__name__)


async def _cancel_task(task: Optional[asyncio.Task[object]]) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug("Background task failed after cancel: %s", exc)


def _make_parsed_query_future(
    parsed_query_cached: Optional[ParsedQuery],
) -> tuple[asyncio.Future[ParsedQuery], Callable[[ParsedQuery], None]]:
    loop = asyncio.get_running_loop()
    parsed_query_future: asyncio.Future[ParsedQuery] = loop.create_future()
    if parsed_query_cached is not None:
        parsed_query_future.set_result(parsed_query_cached)

    def _notify(parsed_query: ParsedQuery) -> None:
        if parsed_query_future.done():
            return
        loop.call_soon_threadsafe(parsed_query_future.set_result, parsed_query)

    return parsed_query_future, _notify


def _create_embedding_task(
    service: SearchServiceLike,
    *,
    parsed_query_future: asyncio.Future[ParsedQuery],
    budget: RequestBudget,
    force_skip_vector_search: bool,
) -> Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]]:
    if force_skip_vector_search:
        budget.skip("embedding")
        budget.skip("vector_search")
        return None
    if not budget.can_afford_vector_search():
        budget.skip("embedding")
        budget.skip("vector_search")
        return None

    async def _maybe_embed_query() -> tuple[Optional[List[float]], int, Optional[str]]:
        parsed_query = await parsed_query_future
        if parsed_query.needs_llm:
            return None, 0, None
        return await embed_query_with_timeout(
            parsed_query.service_query,
            asyncio_module=asyncio,
            embedding_service=service.embedding_service,
            get_config=config_module.get_search_config,
            embedding_soft_timeout_ms=retriever_module.EMBEDDING_SOFT_TIMEOUT_MS,
        )

    return asyncio.create_task(_maybe_embed_query())


async def prepare_uncached_pipeline_for_service(
    service: SearchServiceLike,
    *,
    query: str,
    budget_ms: Optional[int],
    force_high_load: bool,
    force_skip_vector_search: bool,
) -> tuple[
    RequestBudget,
    Optional[ParsedQuery],
    asyncio.Future[ParsedQuery],
    Callable[[ParsedQuery], None],
    Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
]:
    inflight = await runtime._increment_search_inflight()
    soft_limit = max(1, int(config_module.get_search_config().uncached_concurrency))
    if inflight > soft_limit:
        await runtime._decrement_search_inflight()
        logger.warning(
            "[SEARCH] Soft concurrency limit reached, returning 503: query=%s",
            query[:50] if query else "",
        )
        raise HTTPException(
            status_code=503,
            detail="Search temporarily overloaded. Please retry in a few seconds.",
            headers={"Retry-After": "2"},
        )
    effective_budget_ms = (
        budget_ms
        if budget_ms is not None
        else runtime._get_adaptive_budget(inflight, force_high_load=force_high_load)
    )
    budget = RequestBudget(total_ms=effective_budget_ms)
    parsed_query_cached: Optional[ParsedQuery] = None
    try:
        parsed_query_cached = await service.search_cache.get_cached_parsed_query(
            query,
            region_code=service._region_code,
        )
    except Exception as exc:
        logger.warning("Parsed query cache lookup failed: %s", exc)
    parsed_query_future, notify_parsed = _make_parsed_query_future(parsed_query_cached)
    embedding_task = _create_embedding_task(
        service,
        parsed_query_future=parsed_query_future,
        budget=budget,
        force_skip_vector_search=force_skip_vector_search,
    )
    return budget, parsed_query_cached, parsed_query_future, notify_parsed, embedding_task


async def embed_query_with_timeout_for_service(
    service: SearchServiceLike,
    query: str,
) -> tuple[Optional[List[float]], int, Optional[str]]:
    return await embed_query_with_timeout(
        query,
        asyncio_module=asyncio,
        embedding_service=service.embedding_service,
        get_config=config_module.get_search_config,
        embedding_soft_timeout_ms=retriever_module.EMBEDDING_SOFT_TIMEOUT_MS,
    )


def _record_preflight_state(
    *,
    timer: Optional[PipelineTimer],
    pre_data: PreOpenAIData,
    pre_openai_ms: int,
    candidates_flow: Dict[str, int],
    parsed_query: ParsedQuery,
    user_location: Optional[Tuple[float, float]],
) -> None:
    if timer:
        location_tier_value = None
        if pre_data.location_resolution and pre_data.location_resolution.tier is not None:
            try:
                location_tier_value = int(pre_data.location_resolution.tier.value)
            except Exception:
                location_tier_value = None
        timer.record_stage(
            "burst1",
            pre_openai_ms,
            StageStatus.SUCCESS.value,
            {
                "text_candidates": len(pre_data.text_results or {}),
                "region_lookup_loaded": bool(pre_data.region_lookup),
                "location_tier": location_tier_value,
            },
        )
    if candidates_flow:
        candidates_flow["after_text_search"] = len(pre_data.text_results or {})
    if (
        timer
        and parsed_query.location_text
        and parsed_query.location_type != "near_me"
        and user_location is None
    ):
        location_helpers.record_pre_location_tiers(timer, pre_data.location_resolution)


def _start_speculative_tier5_task_for_service(
    service: SearchServiceLike,
    *,
    parsed_query: ParsedQuery,
    pre_data: PreOpenAIData,
    user_location: Optional[Tuple[float, float]],
    budget: RequestBudget,
    force_skip_tier5: bool,
) -> tuple[Optional[location.Tier5Task], Optional[float]]:
    if (
        parsed_query.needs_llm
        or pre_data.location_resolution is not None
        or not pre_data.region_lookup
        or not pre_data.location_llm_candidates
        or not parsed_query.location_text
        or parsed_query.location_type == "near_me"
        or user_location is not None
    ):
        return None, None
    if not budget.can_afford_tier5() or force_skip_tier5:
        budget.skip("tier5_llm")
        return None, None
    started_at = time.perf_counter()
    task = asyncio.create_task(
        location.resolve_location_llm_for_service(
            service,
            location_text=parsed_query.location_text,
            original_query=parsed_query.original_query,
            region_lookup=pre_data.region_lookup,
            candidate_names=pre_data.location_llm_candidates,
        )
    )
    return task, started_at


async def _finalize_preflight_parse_for_service(
    service: SearchServiceLike,
    *,
    query: str,
    user_id: Optional[str],
    parsed_query_cached: Optional[ParsedQuery],
    parsed_query: ParsedQuery,
    embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
    metrics: SearchMetrics,
) -> tuple[ParsedQuery, Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]]]:
    if parsed_query_cached is None and not parsed_query.needs_llm:
        await _cache_parsed_query_safe(service, query, parsed_query)
        return parsed_query, embedding_task
    if not parsed_query.needs_llm:
        return parsed_query, embedding_task
    await _cancel_task(embedding_task)
    parsed_query = await _run_llm_parse_for_service(
        service,
        query=query,
        parsed_query=parsed_query,
        user_id=user_id,
        metrics=metrics,
    )
    return parsed_query, None


async def run_preflight_and_parse_for_service(
    service: SearchServiceLike,
    *,
    query: str,
    user_id: Optional[str],
    user_location: Optional[Tuple[float, float]],
    parsed_query_cached: Optional[ParsedQuery],
    parsed_query_future: asyncio.Future[ParsedQuery],
    notify_parsed: Callable[[ParsedQuery], None],
    embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
    budget: RequestBudget,
    effective_skill_levels: List[str],
    metrics: SearchMetrics,
    timer: Optional[PipelineTimer],
    candidates_flow: Dict[str, int],
    force_skip_tier5: bool,
) -> tuple[
    PreOpenAIData,
    ParsedQuery,
    Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
    Optional[location.Tier5Task],
    Optional[float],
]:
    pre_openai_start = time.perf_counter()
    try:
        pre_data = await asyncio.to_thread(
            run_pre_openai_burst_for_service,
            service,
            query,
            parsed_query=parsed_query_cached,
            user_id=user_id,
            user_location=user_location,
            notify_parsed=notify_parsed,
        )
    except Exception:
        await _cancel_task(embedding_task)
        raise
    pre_openai_ms = int((time.perf_counter() - pre_openai_start) * 1000)
    if not parsed_query_future.done():
        parsed_query_future.set_result(pre_data.parsed_query)
    parsed_query = pre_data.parsed_query
    if effective_skill_levels:
        parsed_query.skill_level = (
            coerce_skill_level_override(effective_skill_levels[0])
            if len(effective_skill_levels) == 1
            else None
        )
    metrics.parse_latency_ms = pre_data.parse_latency_ms
    _record_preflight_state(
        timer=timer,
        pre_data=pre_data,
        pre_openai_ms=pre_openai_ms,
        candidates_flow=candidates_flow,
        parsed_query=parsed_query,
        user_location=user_location,
    )
    tier5_task, tier5_started_at = _start_speculative_tier5_task_for_service(
        service,
        parsed_query=parsed_query,
        pre_data=pre_data,
        user_location=user_location,
        budget=budget,
        force_skip_tier5=force_skip_tier5,
    )
    parsed_query, embedding_task = await _finalize_preflight_parse_for_service(
        service,
        query=query,
        user_id=user_id,
        parsed_query_cached=parsed_query_cached,
        parsed_query=parsed_query,
        embedding_task=embedding_task,
        metrics=metrics,
    )
    if timer:
        timer.record_stage(
            "parse",
            metrics.parse_latency_ms,
            StageStatus.SUCCESS.value,
            {"mode": parsed_query.parsing_mode},
        )
    return pre_data, parsed_query, embedding_task, tier5_task, tier5_started_at


async def resolve_query_embedding_for_service(
    service: SearchServiceLike,
    *,
    parsed_query: ParsedQuery,
    pre_data: PreOpenAIData,
    embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
    budget: RequestBudget,
    metrics: SearchMetrics,
    timer: Optional[PipelineTimer],
    force_skip_vector: bool,
    force_skip_embedding: bool,
) -> tuple[Optional[List[float]], Optional[str]]:
    query_embedding: Optional[List[float]] = None
    embed_latency_ms = 0
    embedding_reason: Optional[str] = None
    budget_skip_vector = False
    # pre_data is produced inside the completed to_thread preflight burst above.
    # After that boundary, this object is only mutated on the event-loop thread.
    force_skip_vector_search = force_skip_vector or force_skip_embedding
    if force_skip_vector_search:
        pre_data.skip_vector = True
        budget_skip_vector = True
        embedding_reason = "force_skip_embedding" if force_skip_embedding else "force_skip_vector"
    if not budget.can_afford_vector_search():
        budget.skip("vector_search")
        budget.skip("embedding")
        pre_data.skip_vector = True
        budget_skip_vector = True
    if pre_data.skip_vector:
        await _cancel_task(embedding_task)
        if embedding_reason is None and budget_skip_vector:
            embedding_reason = "budget_skip_vector_search"
    elif not pre_data.has_service_embeddings:
        await _cancel_task(embedding_task)
        embedding_reason = "no_embeddings_in_database"
    elif embedding_task is not None:
        try:
            query_embedding, embed_latency_ms, embedding_reason = await embedding_task
        except Exception as exc:
            logger.warning("[SEARCH] Embedding failed, falling back to text-only: %s", exc)
            embedding_reason = "embedding_service_unavailable"
    else:
        query_embedding, embed_latency_ms, embedding_reason = await embed_query_with_timeout(
            parsed_query.service_query,
            asyncio_module=asyncio,
            embedding_service=service.embedding_service,
            get_config=config_module.get_search_config,
            embedding_soft_timeout_ms=retriever_module.EMBEDDING_SOFT_TIMEOUT_MS,
        )
    metrics.embed_latency_ms = embed_latency_ms
    if embedding_reason:
        metrics.degraded = True
        metrics.degradation_reasons.append(embedding_reason)
    if timer:
        if pre_data.skip_vector:
            embed_status = StageStatus.SKIPPED.value
        elif embedding_reason == "embedding_timeout":
            embed_status = StageStatus.TIMEOUT.value
        elif embedding_reason in {
            "no_embeddings_in_database",
            "budget_skip_vector_search",
            "force_skip_vector",
            "force_skip_embedding",
        }:
            embed_status = StageStatus.SKIPPED.value
        elif embedding_reason:
            embed_status = StageStatus.ERROR.value
        else:
            embed_status = StageStatus.SUCCESS.value
        timer.record_stage(
            "embedding",
            embed_latency_ms,
            embed_status,
            {"reason": embedding_reason, "used": bool(query_embedding)},
        )
    return query_embedding, embedding_reason


def run_pre_openai_burst_for_service(
    service: SearchServiceLike,
    query: str,
    *,
    parsed_query: Optional[ParsedQuery],
    user_id: Optional[str],
    user_location: Optional[Tuple[float, float]],
    notify_parsed: Optional[Callable[[ParsedQuery], None]] = None,
) -> PreOpenAIData:
    from app.services.search.location_resolver import LocationResolver

    return run_pre_openai_burst(
        get_db_session=database_module.get_db_session,
        search_batch_repository_cls=search_batch_repository_module.SearchBatchRepository,
        query=query,
        parsed_query=parsed_query,
        user_id=user_id,
        user_location=user_location,
        notify_parsed=notify_parsed,
        region_code=service._region_code,
        query_parser_cls=query_parser_module.QueryParser,
        location_resolver_cls=LocationResolver,
        normalize_location_text=location_helpers.normalize_location_text,
        resolve_cached_alias=location_helpers.resolve_cached_alias,
        location_llm_top_k=location.LOCATION_LLM_TOP_K,
        trigram_generic_tokens=retriever_module.TRIGRAM_GENERIC_TOKENS,
        require_text_match_score_threshold=retriever_module.TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD,
        skip_vector_min_results=retriever_module.TEXT_SKIP_VECTOR_MIN_RESULTS,
        skip_vector_score_threshold=retriever_module.TEXT_SKIP_VECTOR_SCORE_THRESHOLD,
        text_top_k=retriever_module.TEXT_TOP_K,
        max_candidates=retriever_module.MAX_CANDIDATES,
        logger=logger,
    )


__all__ = [
    "build_cache_filters",
    "compute_text_match_flags",
    "embed_query_with_timeout",
    "embed_query_with_timeout_for_service",
    "normalize_filter_values",
    "normalize_taxonomy_filter_selections",
    "parse_query",
    "prepare_search_filters",
    "prepare_uncached_pipeline_for_service",
    "resolve_query_embedding_for_service",
    "run_pre_openai_burst",
    "run_pre_openai_burst_for_service",
    "run_preflight_and_parse_for_service",
]
