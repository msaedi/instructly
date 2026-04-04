"""Tier 4 embedding-based location resolution helpers."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, List, Optional

from app.schemas.nl_search import StageStatus
from app.services.search.location_resolver import (
    LocationCandidate,
    LocationResolver,
    ResolutionTier,
    ResolvedLocation,
)
from app.services.search.nl_pipeline.models import PipelineTimer

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import RegionLookup
    from app.services.search.location_embedding_service import LocationEmbeddingService

logger = logging.getLogger(__name__)


async def run_tier4_embedding_search(
    *,
    allow_tier4: bool,
    normalized: str,
    region_lookup: RegionLookup,
    fuzzy_score: Optional[float],
    location_embedding_service: LocationEmbeddingService,
    location_llm_top_k: int,
    llm_embedding_threshold: float,
    diagnostics: Optional[PipelineTimer],
) -> tuple[Optional[ResolvedLocation], List[str]]:
    should_try_embedding = bool(region_lookup.embeddings) and (
        len(normalized.split()) >= 2
        or fuzzy_score is None
        or fuzzy_score >= LocationResolver.MIN_FUZZY_FOR_EMBEDDING
    )
    if not allow_tier4 or not should_try_embedding:
        _record_tier4_skip(
            diagnostics=diagnostics,
            allow_tier4=allow_tier4,
            has_embeddings=bool(region_lookup.embeddings),
        )
        return None, []
    tier4_start = time.perf_counter()
    try:
        embedding = await location_embedding_service.embed_location_text(normalized)
    except Exception as exc:
        logger.warning(
            "Tier 4 embedding search failed for '%s': %s",
            normalized,
            str(exc),
            exc_info=True,
        )
        _record_tier4_error(diagnostics=diagnostics, started_at=tier4_start, error=exc)
        return None, []
    return _build_tier4_result(
        embedding=embedding,
        region_lookup=region_lookup,
        location_llm_top_k=location_llm_top_k,
        llm_embedding_threshold=llm_embedding_threshold,
        diagnostics=diagnostics,
        tier4_start=tier4_start,
    )


def _record_tier4_skip(
    *,
    diagnostics: Optional[PipelineTimer],
    allow_tier4: bool,
    has_embeddings: bool,
) -> None:
    if not diagnostics:
        return
    reason = "disabled"
    if allow_tier4:
        reason = "no_region_embeddings" if not has_embeddings else "fuzzy_threshold"
    diagnostics.record_location_tier(
        tier=4,
        attempted=False,
        status=StageStatus.SKIPPED.value,
        duration_ms=0,
        details=reason,
    )


def _record_tier4_error(
    *,
    diagnostics: Optional[PipelineTimer],
    started_at: float,
    error: Exception,
) -> None:
    if not diagnostics:
        return
    diagnostics.record_location_tier(
        tier=4,
        attempted=True,
        status=StageStatus.ERROR.value,
        duration_ms=int((time.perf_counter() - started_at) * 1000),
        details=str(error),
    )


def _build_tier4_result(
    *,
    embedding: Optional[List[float]],
    region_lookup: RegionLookup,
    location_llm_top_k: int,
    llm_embedding_threshold: float,
    diagnostics: Optional[PipelineTimer],
    tier4_start: float,
) -> tuple[Optional[ResolvedLocation], List[str]]:
    from app.services.search.location_embedding_service import LocationEmbeddingService

    if not embedding:
        if diagnostics:
            diagnostics.record_location_tier(
                tier=4,
                attempted=True,
                status=StageStatus.MISS.value,
                duration_ms=int((time.perf_counter() - tier4_start) * 1000),
                details="no_embedding",
            )
        return None, []
    embedding_rows: List[dict[str, object]] = [
        {
            "region_id": row.region_id,
            "region_name": row.region_name,
            "borough": row.borough,
            "embedding": row.embedding,
            "norm": row.norm,
        }
        for row in region_lookup.embeddings
    ]
    candidates = LocationEmbeddingService.build_candidates_from_embeddings(
        embedding,
        embedding_rows,
        limit=max(location_llm_top_k, 5),
        threshold=min(
            llm_embedding_threshold,
            LocationEmbeddingService.SIMILARITY_THRESHOLD,
        ),
    )
    embedding_candidate_names = _build_embedding_candidate_names(
        candidates=candidates,
        location_llm_top_k=location_llm_top_k,
        llm_embedding_threshold=llm_embedding_threshold,
    )
    resolved = _resolve_tier4_candidate(candidates)
    if diagnostics:
        diagnostics.record_location_tier(
            tier=4,
            attempted=True,
            status=StageStatus.SUCCESS.value if resolved else StageStatus.MISS.value,
            duration_ms=int((time.perf_counter() - tier4_start) * 1000),
            result=(resolved.region_name or resolved.borough) if resolved else None,
            confidence=getattr(resolved, "confidence", None),
            details="embedding_match",
        )
    return resolved, embedding_candidate_names


def _build_embedding_candidate_names(
    *,
    candidates: List[dict[str, object]],
    location_llm_top_k: int,
    llm_embedding_threshold: float,
) -> List[str]:
    ordered_names = [
        str(row["region_name"]).strip()
        for row in candidates
        if row.get("region_name") and _candidate_similarity(row) >= llm_embedding_threshold
    ]
    ordered_names = ordered_names[:location_llm_top_k]
    return list(dict.fromkeys(ordered_names))


def _candidate_similarity(candidate: dict[str, object]) -> float:
    raw_similarity = candidate.get("similarity")
    if isinstance(raw_similarity, (float, int)):
        return float(raw_similarity)
    if isinstance(raw_similarity, str):
        try:
            return float(raw_similarity)
        except ValueError:
            return 0.0
    return 0.0


def _resolve_tier4_candidate(
    candidates: List[dict[str, object]],
) -> Optional[ResolvedLocation]:
    from app.services.search.location_embedding_service import LocationEmbeddingService

    resolver_candidates = [
        row
        for row in candidates
        if _candidate_similarity(row) >= LocationEmbeddingService.SIMILARITY_THRESHOLD
    ][:5]
    best_candidate, ambiguous = LocationEmbeddingService.pick_best_or_ambiguous(resolver_candidates)
    if best_candidate and best_candidate.get("region_id") and best_candidate.get("region_name"):
        return ResolvedLocation.from_region(
            region_id=str(best_candidate["region_id"]),
            region_name=str(best_candidate["region_name"]),
            borough=best_candidate.get("borough"),
            tier=ResolutionTier.EMBEDDING,
            confidence=_candidate_similarity(best_candidate),
        )
    if ambiguous:
        formatted: List[LocationCandidate] = [
            {
                "region_id": str(row["region_id"]),
                "region_name": str(row["region_name"]),
                "borough": row.get("borough"),
            }
            for row in ambiguous
            if row.get("region_id") and row.get("region_name")
        ]
        if len(formatted) >= 2:
            return ResolvedLocation.from_ambiguous(
                candidates=formatted,
                tier=ResolutionTier.EMBEDDING,
                confidence=float(ambiguous[0].get("similarity") or 0.0),
            )
    return None
