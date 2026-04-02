"""Location-resolution helpers for the NL search pipeline."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Callable, List, Optional

from app.schemas.nl_search import StageStatus
from app.services.search import config as config_module
from app.services.search.config import SearchConfig
from app.services.search.location_resolver import ResolvedLocation
from app.services.search.nl_pipeline.location_helpers import (
    build_llm_location_payload,
    consume_task_result,
    parse_llm_location_response,
)
from app.services.search.nl_pipeline.location_runtime import (
    ResolveLocationLLMFn,
    Tier5Result,
    Tier5Task,
    arbitrate_location_result,
    await_tier5_result,
    evaluate_tier5_budget,
    setup_location_resolution,
)
from app.services.search.nl_pipeline.location_tier4 import run_tier4_embedding_search
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PipelineTimer,
    UnresolvedLocationInfo,
)
from app.services.search.nl_pipeline.protocols import LoggerLike, SearchServiceLike

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import RegionLookup
    from app.services.search.location_embedding_service import LocationEmbeddingService
    from app.services.search.location_llm_service import LocationLLMService
    from app.services.search.nl_pipeline.models import PreOpenAIData
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.request_budget import RequestBudget

logger = logging.getLogger(__name__)

LOCATION_LLM_TOP_K = int(os.getenv("LOCATION_LLM_TOP_K", "5"))
LOCATION_TIER4_HIGH_CONFIDENCE = float(os.getenv("LOCATION_TIER4_HIGH_CONFIDENCE", "0.85"))
LOCATION_LLM_CONFIDENCE_THRESHOLD = float(os.getenv("LOCATION_LLM_CONFIDENCE_THRESHOLD", "0.7"))
LOCATION_LLM_EMBEDDING_THRESHOLD = float(os.getenv("LOCATION_LLM_EMBEDDING_THRESHOLD", "0.7"))


async def resolve_location_llm(
    *,
    location_llm_service: LocationLLMService,
    location_text: str,
    original_query: Optional[str],
    region_lookup: RegionLookup,
    candidate_names: List[str],
    timeout_s: Optional[float] = None,
    normalized: Optional[str] = None,
) -> Tier5Result:
    normalized_value, allowed_names, unresolved = build_llm_location_payload(
        location_text=location_text,
        original_query=original_query,
        candidate_names=candidate_names,
        normalized=normalized,
    )
    if not normalized_value:
        return None, None, None
    if unresolved is not None:
        return None, None, unresolved
    llm_result = await location_llm_service.resolve(
        location_text=original_query or location_text,
        allowed_region_names=allowed_names,
        timeout_s=timeout_s,
    )
    return parse_llm_location_response(
        llm_result=llm_result,
        region_lookup=region_lookup,
        normalized_value=normalized_value,
        original_query=original_query,
        location_text=location_text,
    )


async def resolve_location_openai(
    *,
    location_text: str,
    region_lookup: Optional[RegionLookup],
    fuzzy_score: Optional[float],
    original_query: Optional[str],
    llm_candidates: Optional[List[str]],
    tier5_task: Optional[Tier5Task] = None,
    tier5_started_at: Optional[float] = None,
    allow_tier4: bool = True,
    allow_tier5: bool = True,
    force_skip_tier5: bool = False,
    budget: Optional[RequestBudget] = None,
    diagnostics: Optional[PipelineTimer] = None,
    location_embedding_service: LocationEmbeddingService,
    resolve_location_llm_fn: ResolveLocationLLMFn,
    get_config: Callable[[], SearchConfig],
    logger: LoggerLike,
    tier4_high_confidence: float,
    llm_confidence_threshold: float,
    location_llm_top_k: int,
    llm_embedding_threshold: float,
) -> tuple[ResolvedLocation, Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]]:
    normalized, early_result, early_unresolved = setup_location_resolution(
        location_text=location_text,
        region_lookup=region_lookup,
        original_query=original_query,
        tier5_task=tier5_task,
        diagnostics=diagnostics,
        logger=logger,
    )
    if early_result is not None or normalized is None or region_lookup is None:
        return early_result or ResolvedLocation.from_not_found(), None, early_unresolved
    tier4_result, embedding_candidate_names = await run_tier4_embedding_search(
        allow_tier4=allow_tier4,
        normalized=normalized,
        region_lookup=region_lookup,
        fuzzy_score=fuzzy_score,
        location_embedding_service=location_embedding_service,
        location_llm_top_k=location_llm_top_k,
        llm_embedding_threshold=llm_embedding_threshold,
        diagnostics=diagnostics,
    )
    if tier4_result and tier4_result.resolved and tier4_result.confidence >= tier4_high_confidence:
        if tier5_task:
            consume_task_result(tier5_task, label="location_llm", logger=logger)
        if diagnostics:
            diagnostics.record_location_tier(
                tier=5,
                attempted=False,
                status=StageStatus.SKIPPED.value,
                duration_ms=0,
                details="tier4_high_confidence",
            )
        return tier4_result, None, None
    allow_tier5, tier5_timeout_s, tier5_task = evaluate_tier5_budget(
        budget=budget,
        force_skip_tier5=force_skip_tier5,
        tier4_resolved=bool(tier4_result and tier4_result.resolved),
        allow_tier5=allow_tier5,
        tier5_task=tier5_task,
        diagnostics=diagnostics,
        logger=logger,
        get_config=get_config,
    )
    llm_result, llm_cache, llm_unresolved = await await_tier5_result(
        allow_tier5=allow_tier5,
        tier5_task=tier5_task,
        tier5_started_at=tier5_started_at,
        tier5_timeout_s=tier5_timeout_s,
        diagnostics=diagnostics,
        llm_candidates=llm_candidates,
        embedding_candidate_names=embedding_candidate_names,
        region_lookup=region_lookup,
        location_text=location_text,
        original_query=original_query,
        normalized=normalized,
        resolve_location_llm_fn=resolve_location_llm_fn,
        logger=logger,
    )
    return arbitrate_location_result(
        normalized=normalized,
        original_query=original_query,
        location_text=location_text,
        tier4_result=tier4_result,
        llm_result=llm_result,
        llm_cache=llm_cache,
        llm_unresolved=llm_unresolved,
        tier4_high_confidence=tier4_high_confidence,
        llm_confidence_threshold=llm_confidence_threshold,
    )


async def resolve_location_llm_for_service(
    service: SearchServiceLike,
    *,
    location_text: str,
    original_query: Optional[str],
    region_lookup: RegionLookup,
    candidate_names: List[str],
    timeout_s: Optional[float] = None,
    normalized: Optional[str] = None,
) -> Tier5Result:
    return await resolve_location_llm(
        location_llm_service=service.location_llm_service,
        location_text=location_text,
        original_query=original_query,
        region_lookup=region_lookup,
        candidate_names=candidate_names,
        timeout_s=timeout_s,
        normalized=normalized,
    )


async def resolve_location_openai_for_service(
    service: SearchServiceLike,
    location_text: str,
    *,
    region_lookup: Optional[RegionLookup],
    fuzzy_score: Optional[float],
    original_query: Optional[str],
    llm_candidates: Optional[List[str]] = None,
    tier5_task: Optional[Tier5Task] = None,
    tier5_started_at: Optional[float] = None,
    allow_tier4: bool = True,
    allow_tier5: bool = True,
    force_skip_tier5: bool = False,
    budget: Optional[RequestBudget] = None,
    diagnostics: Optional[PipelineTimer] = None,
) -> tuple[ResolvedLocation, Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]]:
    return await resolve_location_openai(
        location_text=location_text,
        region_lookup=region_lookup,
        fuzzy_score=fuzzy_score,
        original_query=original_query,
        llm_candidates=llm_candidates,
        tier5_task=tier5_task,
        tier5_started_at=tier5_started_at,
        allow_tier4=allow_tier4,
        allow_tier5=allow_tier5,
        force_skip_tier5=force_skip_tier5,
        budget=budget,
        diagnostics=diagnostics,
        location_embedding_service=service.location_embedding_service,
        resolve_location_llm_fn=lambda **kwargs: resolve_location_llm_for_service(
            service, **kwargs
        ),
        get_config=config_module.get_search_config,
        logger=logger,
        tier4_high_confidence=LOCATION_TIER4_HIGH_CONFIDENCE,
        llm_confidence_threshold=LOCATION_LLM_CONFIDENCE_THRESHOLD,
        location_llm_top_k=LOCATION_LLM_TOP_K,
        llm_embedding_threshold=LOCATION_LLM_EMBEDDING_THRESHOLD,
    )


async def resolve_location_stage_for_service(
    service: SearchServiceLike,
    *,
    parsed_query: ParsedQuery,
    pre_data: PreOpenAIData,
    user_location: Optional[tuple[float, float]],
    budget: RequestBudget,
    timer: Optional[PipelineTimer],
    force_skip_tier5: bool,
    force_skip_tier4: bool,
    force_skip_embedding: bool,
    tier5_task: Optional[Tier5Task],
    tier5_started_at: Optional[float],
) -> tuple[ResolvedLocation, Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]]:
    location_resolution = pre_data.location_resolution
    location_llm_cache: Optional[LocationLLMCache] = None
    unresolved_info: Optional[UnresolvedLocationInfo] = None
    if (
        user_location is None
        and parsed_query.location_text
        and parsed_query.location_type != "near_me"
    ):
        location_start = time.perf_counter()
        if location_resolution is None:
            allow_tier4 = (
                budget.can_afford_tier4() and not force_skip_tier4 and not force_skip_embedding
            )
            allow_tier5 = budget.can_afford_tier5() and not force_skip_tier5
            if not allow_tier4:
                budget.skip("tier4_embedding")
            if force_skip_tier5:
                budget.skip("tier5_llm")
            (
                location_resolution,
                location_llm_cache,
                unresolved_info,
            ) = await resolve_location_openai_for_service(
                service,
                parsed_query.location_text,
                region_lookup=pre_data.region_lookup,
                fuzzy_score=pre_data.fuzzy_score,
                original_query=parsed_query.original_query,
                llm_candidates=pre_data.location_llm_candidates,
                tier5_task=tier5_task,
                tier5_started_at=tier5_started_at,
                allow_tier4=allow_tier4,
                allow_tier5=allow_tier5,
                force_skip_tier5=force_skip_tier5,
                budget=budget,
                diagnostics=timer,
            )
        if location_resolution is None:
            location_resolution = ResolvedLocation.from_not_found()
        location_ms = int((time.perf_counter() - location_start) * 1000)
        if timer:
            tier_value = None
            if location_resolution and location_resolution.tier is not None:
                try:
                    tier_value = int(location_resolution.tier.value)
                except Exception:
                    tier_value = None
            status = (
                StageStatus.SUCCESS.value
                if location_resolution
                and (location_resolution.resolved or location_resolution.requires_clarification)
                else StageStatus.MISS.value
            )
            timer.record_stage(
                "location_resolution",
                location_ms,
                status,
                {
                    "resolved": bool(location_resolution and location_resolution.resolved),
                    "tier": tier_value,
                },
            )
    elif timer:
        timer.skip_stage("location_resolution", "no_location")
    return (
        location_resolution or ResolvedLocation.from_not_found(),
        location_llm_cache,
        unresolved_info,
    )


__all__ = [
    "LOCATION_LLM_CONFIDENCE_THRESHOLD",
    "LOCATION_LLM_EMBEDDING_THRESHOLD",
    "LOCATION_LLM_TOP_K",
    "LOCATION_TIER4_HIGH_CONFIDENCE",
    "ResolveLocationLLMFn",
    "Tier5Result",
    "Tier5Task",
    "arbitrate_location_result",
    "await_tier5_result",
    "evaluate_tier5_budget",
    "resolve_location_llm",
    "resolve_location_llm_for_service",
    "resolve_location_openai",
    "resolve_location_openai_for_service",
    "resolve_location_stage_for_service",
    "setup_location_resolution",
]
