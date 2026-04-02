"""Shared runtime helpers for multi-tier NL search location resolution."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, List, Optional, TypeAlias

from app.repositories.search_batch_repository import RegionLookup
from app.schemas.nl_search import StageStatus
from app.services.search.config import SearchConfig
from app.services.search.location_resolver import ResolvedLocation
from app.services.search.nl_pipeline.location_helpers import (
    consume_task_result,
    normalize_location_text,
    pick_best_location,
    record_tier5_diagnostics,
)
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PipelineTimer,
    UnresolvedLocationInfo,
)
from app.services.search.nl_pipeline.protocols import LoggerLike
from app.services.search.request_budget import RequestBudget

Tier5Result: TypeAlias = tuple[
    Optional[ResolvedLocation],
    Optional[LocationLLMCache],
    Optional[UnresolvedLocationInfo],
]
Tier5Task: TypeAlias = asyncio.Task[Tier5Result]
ResolveLocationLLMFn: TypeAlias = Callable[..., Awaitable[Tier5Result]]


def setup_location_resolution(
    *,
    location_text: str,
    region_lookup: Optional[RegionLookup],
    original_query: Optional[str],
    tier5_task: Optional[Tier5Task],
    diagnostics: Optional[PipelineTimer],
    logger: LoggerLike,
) -> tuple[Optional[str], Optional[ResolvedLocation], Optional[UnresolvedLocationInfo]]:
    normalized = normalize_location_text(location_text)
    if normalized and region_lookup:
        return normalized, None, None
    if tier5_task:
        consume_task_result(tier5_task, label="location_llm", logger=logger)
    if diagnostics:
        reason = "empty_query" if not normalized else "missing_region_lookup"
        for tier in (4, 5):
            diagnostics.record_location_tier(
                tier=tier,
                attempted=False,
                status=StageStatus.SKIPPED.value,
                duration_ms=0,
                details=reason,
            )
    unresolved = None
    if normalized:
        unresolved = UnresolvedLocationInfo(
            normalized=normalized,
            original_query=original_query or location_text,
        )
    return None, ResolvedLocation.from_not_found(), unresolved


def evaluate_tier5_budget(
    *,
    budget: Optional[RequestBudget],
    force_skip_tier5: bool,
    tier4_resolved: bool,
    allow_tier5: bool,
    tier5_task: Optional[Tier5Task],
    diagnostics: Optional[PipelineTimer],
    logger: LoggerLike,
    get_config: Callable[[], SearchConfig],
) -> tuple[bool, Optional[float], Optional[Tier5Task]]:
    if not budget or budget.can_afford_tier5():
        return allow_tier5, None, tier5_task
    if not force_skip_tier5 and not tier4_resolved and budget.remaining_ms > 0:
        location_timeout_s = max(0.0, float(get_config().location_timeout_ms) / 1000.0)
        tier5_timeout_s = min(budget.remaining_ms / 1000.0, location_timeout_s)
        return True, tier5_timeout_s, tier5_task
    budget.skip("tier5_llm")
    if tier5_task is not None:
        consume_task_result(tier5_task, label="location_llm", logger=logger)
        tier5_task = None
    if diagnostics:
        diagnostics.record_location_tier(
            tier=5,
            attempted=False,
            status=StageStatus.SKIPPED.value,
            duration_ms=0,
            details="budget_insufficient",
        )
    return False, None, tier5_task


async def await_tier5_result(
    *,
    allow_tier5: bool,
    tier5_task: Optional[Tier5Task],
    tier5_started_at: Optional[float],
    tier5_timeout_s: Optional[float],
    diagnostics: Optional[PipelineTimer],
    llm_candidates: Optional[List[str]],
    embedding_candidate_names: List[str],
    region_lookup: RegionLookup,
    location_text: str,
    original_query: Optional[str],
    normalized: str,
    resolve_location_llm_fn: ResolveLocationLLMFn,
    logger: LoggerLike,
) -> Tier5Result:
    if not allow_tier5:
        if tier5_task is not None:
            consume_task_result(tier5_task, label="location_llm", logger=logger)
        elif diagnostics:
            diagnostics.record_location_tier(
                tier=5,
                attempted=False,
                status=StageStatus.SKIPPED.value,
                duration_ms=0,
                details="disabled",
            )
        return None, None, None
    if tier5_task is not None:
        return await _await_existing_tier5_task(
            tier5_task=tier5_task,
            tier5_started_at=tier5_started_at,
            tier5_timeout_s=tier5_timeout_s,
            diagnostics=diagnostics,
            logger=logger,
        )
    allowed_names = _build_allowed_names(
        llm_candidates=llm_candidates,
        embedding_candidate_names=embedding_candidate_names,
        region_lookup=region_lookup,
    )
    if not allowed_names:
        if diagnostics:
            diagnostics.record_location_tier(
                tier=5,
                attempted=False,
                status=StageStatus.SKIPPED.value,
                duration_ms=0,
                details="no_candidates",
            )
        return None, None, None
    return await _run_direct_tier5_call(
        allowed_names=allowed_names,
        tier5_timeout_s=tier5_timeout_s,
        diagnostics=diagnostics,
        location_text=location_text,
        original_query=original_query,
        region_lookup=region_lookup,
        normalized=normalized,
        resolve_location_llm_fn=resolve_location_llm_fn,
        logger=logger,
    )


def _build_allowed_names(
    *,
    llm_candidates: Optional[List[str]],
    embedding_candidate_names: List[str],
    region_lookup: RegionLookup,
) -> List[str]:
    allowed_names = list(llm_candidates or [])
    for name in embedding_candidate_names:
        if name not in allowed_names:
            allowed_names.append(name)
    if allowed_names:
        return allowed_names
    return list(region_lookup.region_names)


async def _await_existing_tier5_task(
    *,
    tier5_task: Tier5Task,
    tier5_started_at: Optional[float],
    tier5_timeout_s: Optional[float],
    diagnostics: Optional[PipelineTimer],
    logger: LoggerLike,
) -> Tier5Result:
    tier5_start = tier5_started_at or time.perf_counter()
    try:
        if tier5_timeout_s and tier5_timeout_s > 0:
            result = await asyncio.wait_for(tier5_task, timeout=tier5_timeout_s)
        else:
            result = await tier5_task
        record_tier5_diagnostics(
            diagnostics,
            tier5_start,
            result[0],
            StageStatus.SUCCESS.value,
            tier5_timeout_s,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("[LOCATION] Tier 5 timed out")
        record_tier5_diagnostics(
            diagnostics, tier5_start, None, StageStatus.TIMEOUT.value, None, "timeout"
        )
    except asyncio.CancelledError:
        record_tier5_diagnostics(
            diagnostics, tier5_start, None, StageStatus.CANCELLED.value, None, "cancelled"
        )
    except Exception as exc:
        logger.warning("[LOCATION] Tier 5 failed: %s", exc)
        record_tier5_diagnostics(
            diagnostics, tier5_start, None, StageStatus.ERROR.value, None, str(exc)
        )
    return None, None, None


async def _run_direct_tier5_call(
    *,
    allowed_names: List[str],
    tier5_timeout_s: Optional[float],
    diagnostics: Optional[PipelineTimer],
    location_text: str,
    original_query: Optional[str],
    region_lookup: RegionLookup,
    normalized: str,
    resolve_location_llm_fn: ResolveLocationLLMFn,
    logger: LoggerLike,
) -> Tier5Result:
    tier5_start = time.perf_counter()
    try:
        result = await resolve_location_llm_fn(
            location_text=location_text,
            original_query=original_query,
            region_lookup=region_lookup,
            candidate_names=allowed_names,
            timeout_s=tier5_timeout_s,
            normalized=normalized,
        )
        detail = f"llm_call candidates={len(allowed_names)}"
        if tier5_timeout_s:
            detail += f" timeout_ms={int(tier5_timeout_s * 1000)}"
        record_tier5_diagnostics(
            diagnostics, tier5_start, result[0], StageStatus.SUCCESS.value, None, detail
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("[LOCATION] Tier 5 timed out")
        record_tier5_diagnostics(
            diagnostics, tier5_start, None, StageStatus.TIMEOUT.value, None, "timeout"
        )
    except Exception as exc:
        logger.warning("[LOCATION] Tier 5 failed: %s", exc)
        record_tier5_diagnostics(
            diagnostics, tier5_start, None, StageStatus.ERROR.value, None, str(exc)
        )
    return None, None, None


def arbitrate_location_result(
    *,
    normalized: str,
    original_query: Optional[str],
    location_text: str,
    tier4_result: Optional[ResolvedLocation],
    llm_result: Optional[ResolvedLocation],
    llm_cache: Optional[LocationLLMCache],
    llm_unresolved: Optional[UnresolvedLocationInfo],
    tier4_high_confidence: float,
    llm_confidence_threshold: float,
) -> tuple[ResolvedLocation, Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]]:
    best = pick_best_location(
        tier4_result,
        llm_result,
        tier4_high_confidence=tier4_high_confidence,
        llm_confidence_threshold=llm_confidence_threshold,
    )
    if not best:
        unresolved = llm_unresolved or UnresolvedLocationInfo(
            normalized=normalized,
            original_query=original_query or location_text,
        )
        return ResolvedLocation.from_not_found(), None, unresolved
    if best is llm_result:
        return best, llm_cache, None
    return best, None, None


__all__ = [
    "ResolveLocationLLMFn",
    "Tier5Result",
    "Tier5Task",
    "arbitrate_location_result",
    "await_tier5_result",
    "evaluate_tier5_budget",
    "setup_location_resolution",
]
