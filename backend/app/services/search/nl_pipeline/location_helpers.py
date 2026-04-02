"""Shared helper functions for location resolution."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, List, Mapping, Optional

from app.schemas.nl_search import StageStatus
from app.services.search.location_resolver import (
    LocationCandidate,
    ResolutionTier,
    ResolvedLocation,
)
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PipelineTimer,
    UnresolvedLocationInfo,
)
from app.services.search.nl_pipeline.protocols import LoggerLike

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import CachedAliasInfo, RegionInfo, RegionLookup

logger = logging.getLogger(__name__)


def normalize_location_text(text_value: str) -> str:
    normalized = " ".join(str(text_value).lower().strip().split())
    for wrapper in ("near ", "by ", "in ", "around ", "close to ", "at "):
        if normalized.startswith(wrapper):
            normalized = normalized[len(wrapper) :]
    if normalized.endswith(" area"):
        normalized = normalized[:-5]
    tokens = normalized.split()
    if len(tokens) >= 3 and tokens[-1] in {"north", "south", "east", "west"}:
        normalized = " ".join(tokens[:-1])
    return " ".join(normalized.strip().split())


def record_pre_location_tiers(
    timer: PipelineTimer,
    location_resolution: Optional[ResolvedLocation],
) -> None:
    tier_map = {
        ResolutionTier.EXACT: 1,
        ResolutionTier.ALIAS: 2,
        ResolutionTier.FUZZY: 3,
    }
    resolved_tier = (
        tier_map.get(location_resolution.tier)
        if location_resolution and location_resolution.tier is not None
        else None
    )
    resolved_name = None
    if location_resolution and (location_resolution.region_name or location_resolution.borough):
        resolved_name = location_resolution.region_name or location_resolution.borough
    for tier in (1, 2, 3):
        if resolved_tier == tier:
            details = (
                "ambiguous"
                if location_resolution and location_resolution.requires_clarification
                else "resolved"
            )
            timer.record_location_tier(
                tier=tier,
                attempted=True,
                status=StageStatus.SUCCESS.value,
                duration_ms=0,
                result=resolved_name,
                confidence=location_resolution.confidence if location_resolution else None,
                details=details,
            )
            continue
        timer.record_location_tier(
            tier=tier,
            attempted=True,
            status=StageStatus.MISS.value,
            duration_ms=0,
            details="miss",
        )


def resolve_cached_alias(
    cached_alias: CachedAliasInfo,
    region_lookup: RegionLookup,
) -> Optional[ResolvedLocation]:
    if cached_alias.is_ambiguous and cached_alias.candidate_region_ids:
        candidates: List[LocationCandidate] = []
        for region_id in cached_alias.candidate_region_ids:
            info = region_lookup.by_id.get(region_id)
            if not info:
                continue
            candidates.append(
                {
                    "region_id": info.region_id,
                    "region_name": info.region_name,
                    "borough": info.borough,
                }
            )
        if len(candidates) >= 2:
            return ResolvedLocation.from_ambiguous(
                candidates=candidates,
                tier=ResolutionTier.LLM,
                confidence=cached_alias.confidence,
            )
    if cached_alias.is_resolved and cached_alias.region_id:
        info = region_lookup.by_id.get(cached_alias.region_id)
        if info:
            return ResolvedLocation.from_region(
                region_id=info.region_id,
                region_name=info.region_name,
                borough=info.borough,
                tier=ResolutionTier.LLM,
                confidence=cached_alias.confidence,
            )
    return None


def distance_region_ids(location_resolution: Optional[ResolvedLocation]) -> Optional[List[str]]:
    if not location_resolution:
        return None
    if location_resolution.region_id:
        return [str(location_resolution.region_id)]
    if location_resolution.requires_clarification and location_resolution.candidates:
        candidate_ids = [
            str(candidate.get("region_id"))
            for candidate in location_resolution.candidates
            if isinstance(candidate, dict) and candidate.get("region_id")
        ]
        return list(dict.fromkeys(candidate_ids)) or None
    return None


def consume_task_result(
    task: asyncio.Task[object],
    *,
    label: str,
    logger: Optional[LoggerLike] = None,
) -> None:
    """Ensure background task exceptions are surfaced without blocking."""
    logger = logger or globals()["logger"]

    def _done(finished: asyncio.Task[object]) -> None:
        try:
            finished.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # pragma: no cover - compatibility logging only
            logger.debug("[SEARCH] %s task failed: %s", label, exc)

    task.add_done_callback(_done)


def pick_best_location(
    tier4_result: Optional[ResolvedLocation],
    tier5_result: Optional[ResolvedLocation],
    *,
    tier4_high_confidence: Optional[float] = None,
    llm_confidence_threshold: Optional[float] = None,
) -> Optional[ResolvedLocation]:
    if tier4_high_confidence is None or llm_confidence_threshold is None:
        from app.services.search.nl_pipeline import location as location_module

        tier4_high_confidence = (
            tier4_high_confidence
            if tier4_high_confidence is not None
            else location_module.LOCATION_TIER4_HIGH_CONFIDENCE
        )
        llm_confidence_threshold = (
            llm_confidence_threshold
            if llm_confidence_threshold is not None
            else location_module.LOCATION_LLM_CONFIDENCE_THRESHOLD
        )
    if tier4_result and tier4_result.resolved and tier4_result.confidence >= tier4_high_confidence:
        return tier4_result
    if tier5_result and (tier5_result.confidence >= llm_confidence_threshold or not tier4_result):
        return tier5_result
    if tier4_result:
        return tier4_result
    return None


def build_llm_location_payload(
    *,
    location_text: str,
    original_query: Optional[str],
    candidate_names: List[str],
    normalized: Optional[str] = None,
) -> tuple[str, List[str], Optional[UnresolvedLocationInfo]]:
    normalized_value = normalized or normalize_location_text(location_text)
    if not normalized_value:
        return "", [], None
    allowed_names: List[str] = []
    seen: set[str] = set()
    for name in candidate_names:
        if not name:
            continue
        key = str(name).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        allowed_names.append(str(name).strip())
    unresolved = None
    if not allowed_names:
        unresolved = UnresolvedLocationInfo(
            normalized=normalized_value,
            original_query=original_query or location_text,
        )
    return normalized_value, allowed_names, unresolved


def parse_llm_location_response(
    *,
    llm_result: Optional[Mapping[str, object]],
    region_lookup: RegionLookup,
    normalized_value: str,
    original_query: Optional[str],
    location_text: str,
) -> tuple[
    Optional[ResolvedLocation], Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]
]:
    unresolved = UnresolvedLocationInfo(
        normalized=normalized_value,
        original_query=original_query or location_text,
    )
    neighborhoods = llm_result.get("neighborhoods") if llm_result else None
    if not isinstance(neighborhoods, list) or not neighborhoods:
        return None, None, unresolved
    regions: List[RegionInfo] = []
    seen_ids: set[str] = set()
    for name in neighborhoods:
        if not isinstance(name, str):
            continue
        info = region_lookup.by_name.get(name.strip().lower())
        if not info or info.region_id in seen_ids:
            continue
        seen_ids.add(info.region_id)
        regions.append(info)
    if not regions:
        return None, None, unresolved
    raw_confidence = llm_result.get("confidence") if llm_result else None
    if isinstance(raw_confidence, (str, int, float)):
        try:
            confidence_val = float(raw_confidence)
        except ValueError:
            confidence_val = 0.5
    else:
        confidence_val = 0.5
    llm_cache = LocationLLMCache(
        normalized=normalized_value,
        confidence=confidence_val,
        region_ids=[region.region_id for region in regions],
    )
    if len(regions) == 1:
        region = regions[0]
        return (
            ResolvedLocation.from_region(
                region_id=region.region_id,
                region_name=region.region_name,
                borough=region.borough,
                tier=ResolutionTier.LLM,
                confidence=confidence_val,
            ),
            llm_cache,
            None,
        )
    candidates: List[LocationCandidate] = [
        {
            "region_id": region.region_id,
            "region_name": region.region_name,
            "borough": region.borough,
        }
        for region in regions
    ]
    return (
        ResolvedLocation.from_ambiguous(
            candidates=candidates,
            tier=ResolutionTier.LLM,
            confidence=confidence_val,
        ),
        llm_cache,
        None,
    )


def record_tier5_diagnostics(
    diagnostics: Optional[PipelineTimer],
    started_at: float,
    llm_result: Optional[ResolvedLocation],
    status: str,
    timeout_s: Optional[float],
    details: Optional[str] = None,
) -> None:
    if not diagnostics:
        return
    detail_text = details
    if detail_text is None and timeout_s:
        detail_text = f"llm_task timeout_ms={int(timeout_s * 1000)}"
    elif detail_text is None:
        detail_text = "llm_task"
    diagnostics.record_location_tier(
        tier=5,
        attempted=True,
        status=status
        if llm_result or status != StageStatus.SUCCESS.value
        else StageStatus.MISS.value,
        duration_ms=int((time.perf_counter() - started_at) * 1000),
        result=(llm_result.region_name or llm_result.borough) if llm_result else None,
        confidence=getattr(llm_result, "confidence", None),
        details=detail_text,
    )
