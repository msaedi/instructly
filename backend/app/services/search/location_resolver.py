"""
Location resolver for NL search.

Phase 1 supports a 5-tier pipeline (Tier 4/5 are optional):
1) Exact match on `region_boundaries.region_name`
2) Alias lookup in `location_aliases` (trust + ambiguity model)
2.5) Substring match on `region_boundaries.region_name`
3) Fuzzy match via pg_trgm `similarity()` on `region_boundaries.region_name`
4) Embedding similarity (OpenAI + pgvector)
5) LLM mapping (OpenAI)

Notes:
- `region_boundaries` is the source of truth for neighborhood names.
- Borough inputs are treated as a parent_region filter (no need for a borough boundary row).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import json
import logging
import os
from pathlib import Path
import time as time_module
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, Sequence, TypedDict

from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.location_alias import NYC_CITY_ID, LocationAlias
from app.models.region_boundary import RegionBoundary
from app.repositories.location_resolution_repository import LocationResolutionRepository
from app.repositories.unresolved_location_query_repository import (
    UnresolvedLocationQueryRepository,
)
from app.services.search.location_embedding_service import LocationEmbeddingService
from app.services.search.location_llm_service import LocationLLMService

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import RegionLookup

logger = logging.getLogger(__name__)

# Optional perf logging for profiling in staging/dev.
# NOTE: Read at module load time — changes require process restart.
_PERF_LOG_ENABLED = os.getenv("NL_SEARCH_PERF_LOG") == "1"
_PERF_LOG_SLOW_MS = int(os.getenv("NL_SEARCH_PERF_LOG_SLOW_MS", "0"))

_LOCATION_ALIASES_JSON_PATH = Path(__file__).resolve().parents[3] / "data" / "location_aliases.json"


@lru_cache(maxsize=16)
def _load_location_alias_seed_maps(
    region_code: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """
    Load alias -> region_name / candidates mapping from `backend/data/location_aliases.json`.

    This is a best-effort fallback used when the DB seeder was not run or when canonical
    `region_boundaries.region_name` values differ from the JSON's human labels.
    """
    try:
        payload = json.loads(_LOCATION_ALIASES_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, {}
    except Exception as exc:
        logger.warning(
            "Failed to load location_aliases.json: %s",
            str(exc),
            exc_info=True,
        )
        return {}, {}

    if str(payload.get("region_code") or "").strip().lower() != str(region_code).strip().lower():
        return {}, {}

    resolved: dict[str, dict[str, Any]] = {}
    for row in payload.get("aliases") or []:
        if not isinstance(row, dict):
            continue
        alias = row.get("alias")
        if not alias:
            continue
        key = " ".join(str(alias).strip().lower().split())
        if key:
            resolved[key] = row

    ambiguous: dict[str, dict[str, Any]] = {}
    for row in payload.get("ambiguous_aliases") or []:
        if not isinstance(row, dict):
            continue
        alias = row.get("alias")
        if not alias:
            continue
        key = " ".join(str(alias).strip().lower().split())
        if key:
            ambiguous[key] = row

    return resolved, ambiguous


def _unique_sorted_region_ids(region_ids: Sequence[object] | None) -> list[str]:
    return sorted({str(region_id) for region_id in (region_ids or []) if region_id})


def _logical_region_name(*, region_name: object, display_name: object) -> str:
    display = str(display_name or "").strip()
    if display:
        return display
    return str(region_name or "").strip()


class ResolutionTier(Enum):
    EXACT = 1
    ALIAS = 2
    FUZZY = 3
    EMBEDDING = 4
    LLM = 5
    NOT_FOUND = 0


class LocationCandidate(TypedDict):
    region_id: str
    region_name: str
    borough: str | None


class LocationCandidateDisplay(LocationCandidate, total=False):
    display_name: str | None
    display_key: str | None
    region_ids: List[str]


@dataclass(frozen=True)
class ResolvedLocation:
    """Result of location resolution."""

    # Resolution status
    resolved: bool = False
    not_found: bool = False
    requires_clarification: bool = False

    # Resolved data (if resolved=True)
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    borough: Optional[str] = None
    region_ids: Optional[List[str]] = None

    # Ambiguous data (if requires_clarification=True)
    candidates: Optional[List[LocationCandidateDisplay]] = None

    # Metadata
    tier: Optional[ResolutionTier] = None
    confidence: float = 0.0
    method: str = "none"  # 'exact', 'alias', 'fuzzy', 'embedding', 'llm', 'none'

    @property
    def kind(self) -> str:
        """Back-compat helper: 'region' | 'borough' | 'none'."""
        if self.requires_clarification:
            return "none"
        if self.region_id:
            return "region"
        if self.borough:
            return "borough"
        return "none"

    @classmethod
    def from_region(
        cls,
        *,
        region_id: str,
        region_name: str,
        borough: Optional[str],
        region_ids: Optional[Sequence[str]] = None,
        tier: ResolutionTier,
        confidence: float,
    ) -> "ResolvedLocation":
        return cls(
            resolved=True,
            region_id=region_id,
            region_name=region_name,
            borough=borough,
            region_ids=_unique_sorted_region_ids(region_ids or [region_id]),
            tier=tier,
            confidence=confidence,
            method=tier.name.lower(),
        )

    @classmethod
    def from_borough(
        cls,
        *,
        borough: str,
        tier: ResolutionTier,
        confidence: float,
    ) -> "ResolvedLocation":
        return cls(
            resolved=True,
            borough=borough,
            tier=tier,
            confidence=confidence,
            method=tier.name.lower(),
        )

    @classmethod
    def from_ambiguous(
        cls,
        *,
        candidates: List[LocationCandidateDisplay],
        tier: ResolutionTier,
        confidence: float,
    ) -> "ResolvedLocation":
        return cls(
            requires_clarification=True,
            candidates=candidates,
            tier=tier,
            confidence=confidence,
            method=tier.name.lower(),
        )

    @classmethod
    def from_not_found(cls) -> "ResolvedLocation":
        return cls(not_found=True, tier=ResolutionTier.NOT_FOUND, confidence=0.0, method="none")


class LocationResolver:
    """
    Resolves user location input to `region_boundaries` or a borough filter.

    Tier 1-3 are synchronous and fast; Tier 4/5 are async OpenAI calls.
    """

    # Thresholds (calibrate via eval harness)
    FUZZY_THRESHOLD = 0.4
    # Minimum fuzzy score to attempt embedding tier - prevents false positives on nonsense
    # (e.g., "madeupplace" has 0.18 fuzzy score, below this threshold, so skip embedding)
    MIN_FUZZY_FOR_EMBEDDING = 0.25

    _BOROUGH_CANONICAL = {
        "manhattan": "Manhattan",
        "brooklyn": "Brooklyn",
        "queens": "Queens",
        "bronx": "Bronx",
        "staten island": "Staten Island",
    }

    _BOROUGH_ALIASES = {
        "bk": "brooklyn",
        "bklyn": "brooklyn",
        "kings county": "brooklyn",
        "bx": "bronx",
        "the bronx": "bronx",
        "qns": "queens",
        "si": "staten island",
        "staten": "staten island",
        "richmond county": "staten island",
    }

    def __init__(
        self,
        db: Session,
        region_code: str = "nyc",
        *,
        city_id: str = NYC_CITY_ID,
        repository: Optional[LocationResolutionRepository] = None,
        unresolved_repository: Optional[UnresolvedLocationQueryRepository] = None,
        region_lookup: RegionLookup | None = None,
    ) -> None:
        self.region_code = region_code
        self.city_id = city_id
        self._region_lookup = region_lookup
        self.repository = repository or LocationResolutionRepository(
            db, region_code=region_code, city_id=city_id
        )
        self.unresolved_repository = unresolved_repository or UnresolvedLocationQueryRepository(
            db, city_id=city_id
        )
        self.embedding_service = LocationEmbeddingService(self.repository)
        self.llm_service = LocationLLMService()

    async def resolve(
        self,
        location_text: str,
        *,
        original_query: Optional[str] = None,
        track_unresolved: bool = False,
        enable_semantic: bool = False,
    ) -> ResolvedLocation:
        """
        Resolve a user-entered location string to a region boundary or borough.

        If `track_unresolved=True`, unresolved location texts are persisted to
        `unresolved_location_queries` for later analysis.
        """
        perf_start = time_module.perf_counter() if _PERF_LOG_ENABLED else 0.0
        perf: dict[str, int] = {} if _PERF_LOG_ENABLED else {}

        def _finalize(result: ResolvedLocation) -> ResolvedLocation:
            if not _PERF_LOG_ENABLED:
                return result
            total_ms = int((time_module.perf_counter() - perf_start) * 1000)
            if total_ms < _PERF_LOG_SLOW_MS:
                return result
            logger.info(
                "NL location resolution timings: %s",
                {
                    **perf,
                    "total_ms": total_ms,
                    "method": result.method,
                    "resolved": bool(result.resolved),
                    "ambiguous": bool(result.requires_clarification),
                    "not_found": bool(result.not_found),
                    "region_code": self.region_code,
                },
            )
            return result

        if not location_text:
            return ResolvedLocation.from_not_found()

        normalized = self._normalize(location_text)
        if not normalized or len(normalized) < 2:
            return ResolvedLocation.from_not_found()

        result = await asyncio.to_thread(self._resolve_non_semantic, normalized, perf)
        if result is not None:
            return _finalize(result)

        if enable_semantic:
            tokens = normalized.split()

            # Gate embedding tier for single-token inputs: if fuzzy score is too low, the query is
            # likely nonsense (e.g., "madeupplace" has a very low fuzzy score) and embedding
            # similarity can produce surprising false positives.
            #
            # Multi-token inputs (e.g., "museum mile", "central park") are more likely to be
            # meaningful landmarks; allow Tier 4 even if fuzzy similarity to neighborhood names is low.
            should_try_embedding = len(tokens) >= 2
            best_fuzzy_score: float | None = None

            if not should_try_embedding:
                fuzzy_gate_start = time_module.perf_counter()
                best_fuzzy_score = await asyncio.to_thread(
                    self.repository.get_best_fuzzy_score, normalized
                )
                if _PERF_LOG_ENABLED:
                    perf["fuzzy_gate_ms"] = int(
                        (time_module.perf_counter() - fuzzy_gate_start) * 1000
                    )
                should_try_embedding = (
                    best_fuzzy_score is not None
                    and best_fuzzy_score >= self.MIN_FUZZY_FOR_EMBEDDING
                )

            if should_try_embedding:
                tier_start = time_module.perf_counter()
                tier4 = await self._tier4_embedding_match(normalized)
                if _PERF_LOG_ENABLED:
                    perf["tier4_embedding_ms"] = int(
                        (time_module.perf_counter() - tier_start) * 1000
                    )
                if tier4.resolved or tier4.requires_clarification:
                    return _finalize(tier4)
            elif best_fuzzy_score is not None:
                logger.debug(
                    "Skipping embedding tier for '%s' - fuzzy score %.2f < %.2f threshold",
                    normalized,
                    best_fuzzy_score,
                    self.MIN_FUZZY_FOR_EMBEDDING,
                )

            tier_start = time_module.perf_counter()
            tier5 = await self._tier5_llm_match(
                normalized, original_query=original_query or location_text
            )
            if _PERF_LOG_ENABLED:
                perf["tier5_llm_ms"] = int((time_module.perf_counter() - tier_start) * 1000)
            if tier5.resolved or tier5.requires_clarification:
                return _finalize(tier5)

        if track_unresolved:
            await asyncio.to_thread(
                self.unresolved_repository.track_unresolved,
                normalized,
                original_query=original_query or location_text,
            )
            logger.info("Tracked unresolved location '%s' (city_id=%s)", normalized, self.city_id)

        return _finalize(ResolvedLocation.from_not_found())

    def resolve_sync(
        self,
        location_text: str,
        *,
        original_query: Optional[str] = None,
        track_unresolved: bool = False,
    ) -> ResolvedLocation:
        """
        Resolve a location string using only Tier 0-3 logic (no OpenAI calls).
        """
        perf_start = time_module.perf_counter() if _PERF_LOG_ENABLED else 0.0
        perf: dict[str, int] = {} if _PERF_LOG_ENABLED else {}

        def _finalize(result: ResolvedLocation) -> ResolvedLocation:
            if not _PERF_LOG_ENABLED:
                return result
            total_ms = int((time_module.perf_counter() - perf_start) * 1000)
            if total_ms < _PERF_LOG_SLOW_MS:
                return result
            logger.info(
                "NL location resolution timings: %s",
                {
                    **perf,
                    "total_ms": total_ms,
                    "method": result.method,
                    "resolved": bool(result.resolved),
                    "ambiguous": bool(result.requires_clarification),
                    "not_found": bool(result.not_found),
                    "region_code": self.region_code,
                },
            )
            return result

        if not location_text:
            return ResolvedLocation.from_not_found()

        normalized = self._normalize(location_text)
        if not normalized or len(normalized) < 2:
            return ResolvedLocation.from_not_found()

        result = self._resolve_non_semantic(normalized, perf)
        if result is not None:
            return _finalize(result)

        if track_unresolved:
            self.unresolved_repository.track_unresolved(
                normalized, original_query=original_query or location_text
            )
            logger.info("Tracked unresolved location '%s' (city_id=%s)", normalized, self.city_id)

        return _finalize(ResolvedLocation.from_not_found())

    def _resolve_non_semantic(
        self,
        normalized: str,
        perf: dict[str, int],
    ) -> Optional[ResolvedLocation]:
        # Tier 0: Borough aliases (no DB dependency)
        borough_key = self._BOROUGH_ALIASES.get(normalized)
        if borough_key:
            return ResolvedLocation.from_borough(
                borough=self._BOROUGH_CANONICAL[borough_key],
                tier=ResolutionTier.ALIAS,
                confidence=1.0,
            )

        # Tier 1: Exact match (includes borough names)
        tier_start = time_module.perf_counter()
        exact = self._tier1_exact_match(normalized)
        if _PERF_LOG_ENABLED:
            perf["tier1_exact_ms"] = int((time_module.perf_counter() - tier_start) * 1000)
        if exact.resolved:
            return exact

        # Tier 2: Alias lookup (trust + ambiguity)
        tier_start = time_module.perf_counter()
        alias_result = self._tier2_alias_lookup(normalized)
        if _PERF_LOG_ENABLED:
            perf["tier2_alias_ms"] = int((time_module.perf_counter() - tier_start) * 1000)
        if alias_result.resolved or alias_result.requires_clarification:
            return alias_result

        # Tier 2.5: Substring match on region_boundaries (e.g., "carnegie" -> "Upper East Side-Carnegie Hill")
        tier_start = time_module.perf_counter()
        substring = self._tier2_5_region_name_substring(normalized)
        if _PERF_LOG_ENABLED:
            perf["tier2_5_substring_ms"] = int((time_module.perf_counter() - tier_start) * 1000)
        if substring.resolved or substring.requires_clarification:
            return substring

        # Tier 3: Fuzzy match (pg_trgm similarity)
        tier_start = time_module.perf_counter()
        fuzzy = self._tier3_fuzzy_match(normalized)
        if _PERF_LOG_ENABLED:
            perf["tier3_fuzzy_ms"] = int((time_module.perf_counter() - tier_start) * 1000)
        if fuzzy.resolved:
            return fuzzy

        return None

    def _normalize(self, text_value: str) -> str:
        normalized = " ".join(str(text_value).lower().strip().split())
        wrappers = ("near ", "by ", "in ", "around ", "close to ", "at ")
        for wrapper in wrappers:
            if normalized.startswith(wrapper):
                normalized = normalized[len(wrapper) :]
        if normalized.endswith(" area"):
            normalized = normalized[:-5]
        # Common "landmark + direction" inputs (e.g., "central park north") should
        # still resolve via the base landmark ("central park") if needed.
        tokens = normalized.split()
        if len(tokens) >= 3 and tokens[-1] in {"north", "south", "east", "west"}:
            normalized = " ".join(tokens[:-1])
        return " ".join(normalized.strip().split())

    def _tier1_exact_match(self, normalized: str) -> ResolvedLocation:
        borough_name = self._BOROUGH_CANONICAL.get(normalized)
        if borough_name:
            return ResolvedLocation.from_borough(
                borough=borough_name,
                tier=ResolutionTier.EXACT,
                confidence=1.0,
            )

        region = self.repository.find_exact_region_by_name(normalized)
        if region and getattr(region, "id", None) and getattr(region, "region_name", None):
            regions = self._expand_regions_for_logical_resolution([region])
            candidates = self._dedupe_candidates_by_display(self._format_candidates(regions))
            return self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.EXACT,
                confidence=1.0,
            )

        return ResolvedLocation.from_not_found()

    def _tier2_alias_lookup(self, normalized: str) -> ResolvedLocation:
        alias_row = self.repository.find_trusted_alias(normalized)
        if not alias_row:
            return self._tier2_alias_lookup_from_seed_data(normalized)

        self.repository.increment_alias_user_count(alias_row)

        if alias_row.is_ambiguous and alias_row.candidate_region_ids:
            regions = self.repository.get_regions_by_ids(list(alias_row.candidate_region_ids))
            candidates = self._dedupe_candidates_by_display(self._format_candidates(regions))
            result = self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.ALIAS,
                confidence=float(alias_row.confidence or 1.0),
            )
            if result.resolved or result.requires_clarification:
                return result

        if alias_row.is_resolved and alias_row.region_boundary_id:
            supporting_ids = _unique_sorted_region_ids(
                [str(alias_row.region_boundary_id), *(alias_row.candidate_region_ids or [])]
            )
            regions = self.repository.get_regions_by_ids(supporting_ids)
            if not regions:
                region = self.repository.get_region_by_id(str(alias_row.region_boundary_id))
                regions = [region] if region else []
            logical_regions = self._expand_regions_for_logical_resolution(regions)
            candidates = self._dedupe_candidates_by_display(
                self._format_candidates(logical_regions)
            )
            result = self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.ALIAS,
                confidence=float(alias_row.confidence or 1.0),
            )
            if result.resolved or result.requires_clarification:
                return result

        return ResolvedLocation.from_not_found()

    def _tier2_alias_lookup_from_seed_data(self, normalized: str) -> ResolvedLocation:
        """
        Best-effort alias lookup from `backend/data/location_aliases.json`.

        This keeps common abbreviations working even if:
        - the system seeder hasn't been run yet, or
        - region_boundaries names don't exactly match the JSON labels (sub-neighborhoods, suffixes, etc.)
        """
        resolved_map, ambiguous_map = _load_location_alias_seed_maps(self.region_code)
        payload_row = resolved_map.get(normalized) or ambiguous_map.get(normalized)
        if not payload_row:
            return ResolvedLocation.from_not_found()

        confidence = float(payload_row.get("confidence") or 1.0)

        # Resolved alias: map region_name label -> region_boundaries rows
        region_label = payload_row.get("region_name")
        if region_label:
            label_norm = self._normalize(str(region_label))
            exact = self.repository.find_exact_region_by_name(label_norm)
            if exact and getattr(exact, "id", None) and getattr(exact, "region_name", None):
                regions = self._expand_regions_for_logical_resolution([exact])
                candidates = self._dedupe_candidates_by_display(self._format_candidates(regions))
                return self._build_result_from_candidates(
                    candidates,
                    tier=ResolutionTier.ALIAS,
                    confidence=confidence,
                )

            fragment_regions = self.repository.find_regions_by_name_fragment(label_norm)
            candidates = self._dedupe_candidates_by_display(
                self._format_candidates(fragment_regions)
            )
            candidates = self._prefer_exact_logical_candidates(label_norm, candidates)
            return self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.ALIAS,
                confidence=confidence,
            )

        # Ambiguous alias: map candidate labels -> region_boundaries rows (union)
        candidate_labels = payload_row.get("candidates") or []
        if isinstance(candidate_labels, list):
            all_regions: list[RegionBoundary] = []
            for label in candidate_labels:
                if not label:
                    continue
                label_norm = self._normalize(str(label))
                exact = self.repository.find_exact_region_by_name(label_norm)
                if exact:
                    all_regions.append(exact)
                    continue
                all_regions.extend(self.repository.find_regions_by_name_fragment(label_norm))

            # Deduplicate by region id
            by_id: dict[str, RegionBoundary] = {}
            for region in all_regions:
                if getattr(region, "id", None):
                    by_id[str(region.id)] = region

            candidates = self._dedupe_candidates_by_display(
                self._format_candidates(list(by_id.values()))
            )
            candidates = self._prefer_exact_logical_candidates(normalized, candidates)
            return self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.ALIAS,
                confidence=confidence,
            )

        return ResolvedLocation.from_not_found()

    def _tier2_5_region_name_substring(self, normalized: str) -> ResolvedLocation:
        """
        Substring match on `region_boundaries.region_name` for partial neighborhood inputs.

        Examples:
        - "carnegie" -> "Upper East Side-Carnegie Hill"
        - "yorkville" -> "Upper East Side-Yorkville"

        If multiple matches exist (e.g., "midtown"), returns an ambiguous result with a small
        candidate set so downstream filtering can apply a union coverage filter.
        """
        # Avoid extremely short tokens which tend to match too broadly ("east", "west", etc.).
        if len(normalized) < 4:
            return ResolvedLocation.from_not_found()

        regions = self.repository.find_regions_by_name_fragment(normalized)
        if not regions:
            return ResolvedLocation.from_not_found()

        raw_candidates = self._format_candidates(regions)
        candidates = self._dedupe_candidates_by_display(raw_candidates)
        candidates = self._prefer_exact_logical_candidates(normalized, candidates)
        if len(candidates) > 5:
            candidates = sorted(
                candidates,
                key=lambda candidate: len(self._candidate_logical_name(candidate)),
            )[:5]
        return self._build_result_from_candidates(
            candidates,
            tier=ResolutionTier.FUZZY,
            confidence=0.9,
        )

    def _tier3_fuzzy_match(self, normalized: str) -> ResolvedLocation:
        region, similarity = self.repository.find_best_fuzzy_region(
            normalized, threshold=self.FUZZY_THRESHOLD
        )
        if region and getattr(region, "id", None) and getattr(region, "region_name", None):
            regions = self._expand_regions_for_logical_resolution([region])
            candidates = self._dedupe_candidates_by_display(self._format_candidates(regions))
            return self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.FUZZY,
                confidence=float(similarity or 0.0),
            )
        return ResolvedLocation.from_not_found()

    async def _tier4_embedding_match(self, normalized: str) -> ResolvedLocation:
        """Tier 4: Semantic match using OpenAI embeddings + pgvector on region_boundaries."""
        candidates = await self.embedding_service.get_candidates(normalized, limit=5)
        logical_candidates = self._dedupe_candidates_by_display(candidates)
        best, ambiguous = self.embedding_service.pick_best_or_ambiguous(logical_candidates)

        if best and best.get("region_id") and best.get("region_name"):
            return ResolvedLocation.from_region(
                region_id=str(best["region_id"]),
                region_name=self._candidate_logical_name(best),
                borough=best.get("borough"),
                region_ids=self._candidate_region_ids(best),
                tier=ResolutionTier.EMBEDDING,
                confidence=float(best.get("similarity") or 0.0),
            )

        if ambiguous:
            top_sim = float(ambiguous[0].get("similarity") or 0.0)
            return self._build_result_from_candidates(
                ambiguous,
                tier=ResolutionTier.EMBEDDING,
                confidence=top_sim,
            )

        return ResolvedLocation.from_not_found()

    async def _tier5_llm_match(
        self,
        normalized: str,
        *,
        original_query: str,
    ) -> ResolvedLocation:
        """
        Tier 5: LLM-based resolution (cached in location_aliases as pending_review).

        This tier is designed for landmark-style inputs that don't match well via substring/fuzzy/embeddings.
        """

        def _load_cached() -> (
            tuple[
                Optional[LocationAlias],
                Optional[list[RegionBoundary]],
                Optional[str],
            ]
        ):
            cached = self.repository.find_cached_alias(normalized, source="llm")
            if not cached:
                return None, None, None

            self.repository.increment_alias_user_count(cached)

            if cached.is_ambiguous and cached.candidate_region_ids:
                candidate_regions = self.repository.get_regions_by_ids(
                    list(cached.candidate_region_ids)
                )
                return cached, candidate_regions, "ambiguous"

            if cached.is_resolved and cached.region_boundary_id:
                supporting_ids = _unique_sorted_region_ids(
                    [str(cached.region_boundary_id), *(cached.candidate_region_ids or [])]
                )
                supporting_regions = self.repository.get_regions_by_ids(supporting_ids)
                if not supporting_regions:
                    region = self.repository.get_region_by_id(str(cached.region_boundary_id))
                    supporting_regions = [region] if region else []
                return cached, supporting_regions, "resolved"

            return cached, [], None

        cached, cached_regions, cached_kind = await asyncio.to_thread(_load_cached)
        if cached and cached_kind == "ambiguous":
            candidates = self._dedupe_candidates_by_display(
                self._format_candidates(cached_regions or [])
            )
            result = self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.LLM,
                confidence=float(cached.confidence or 0.5),
            )
            if result.resolved or result.requires_clarification:
                return result
        if cached and cached_kind == "resolved":
            resolved_cached_regions = self._expand_regions_for_logical_resolution(
                cached_regions or []
            )
            candidates = self._dedupe_candidates_by_display(
                self._format_candidates(resolved_cached_regions)
            )
            result = self._build_result_from_candidates(
                candidates,
                tier=ResolutionTier.LLM,
                confidence=float(cached.confidence or 0.5),
            )
            if result.resolved or result.requires_clarification:
                return result

        allowed_names = await asyncio.to_thread(self.repository.list_region_names)
        llm_result = await self.llm_service.resolve(
            location_text=original_query,
            allowed_region_names=allowed_names,
        )
        if not llm_result:
            return ResolvedLocation.from_not_found()

        neighborhoods = llm_result.get("neighborhoods") or []
        if not isinstance(neighborhoods, list) or not neighborhoods:
            return ResolvedLocation.from_not_found()

        def _load_llm_regions() -> list[RegionBoundary]:
            regions: list[RegionBoundary] = []
            for name in neighborhoods:
                if not isinstance(name, str) or not name.strip():
                    continue
                name_norm = " ".join(name.strip().lower().split())
                exact = self.repository.find_exact_region_by_name(name_norm)
                if exact:
                    regions.append(exact)
                    continue
                # Best-effort fallback (should be rare because LLM is constrained to allowed list).
                regions.extend(self.repository.find_regions_by_name_fragment(name_norm))

            by_id: dict[str, RegionBoundary] = {}
            for region in regions:
                if getattr(region, "id", None):
                    by_id[str(region.id)] = region
            return list(by_id.values())

        resolved_regions = await asyncio.to_thread(_load_llm_regions)

        if not resolved_regions:
            return ResolvedLocation.from_not_found()

        confidence_val = float(llm_result.get("confidence") or 0.5)
        logical_regions = self._expand_regions_for_logical_resolution(resolved_regions)
        candidates = self._dedupe_candidates_by_display(self._format_candidates(logical_regions))
        await asyncio.to_thread(
            self.cache_llm_alias,
            normalized,
            self._collect_candidate_region_ids(candidates),
            confidence=confidence_val,
        )
        return self._build_result_from_candidates(
            candidates,
            tier=ResolutionTier.LLM,
            confidence=confidence_val,
        )

    def cache_llm_alias(
        self,
        normalized: str,
        resolved_region_ids: List[str],
        *,
        confidence: float,
    ) -> None:
        """Cache an LLM-derived alias as pending_review (best-effort)."""
        deduped_input_ids = _unique_sorted_region_ids(resolved_region_ids)
        if not normalized or not deduped_input_ids:
            return

        try:
            existing_any = self.repository.find_cached_alias(normalized)
            if existing_any and isinstance(existing_any, LocationAlias):
                alias_row = existing_any
                alias_row.source = "llm"
                alias_row.status = "pending_review"
                alias_row.confidence = confidence
                alias_row.alias_type = "landmark"
                alias_row.deprecated_at = None
                alias_row.user_count = int(alias_row.user_count or 0) + 1
            else:
                alias_row = LocationAlias(
                    id=generate_ulid(),
                    city_id=self.city_id,
                    alias_normalized=normalized,
                    source="llm",
                    status="pending_review",
                    confidence=confidence,
                    user_count=1,
                    alias_type="landmark",
                )
                self.repository.db.add(alias_row)

            regions: Sequence[object] = self.repository.get_regions_by_ids(deduped_input_ids)
            regions = self._expand_regions_for_logical_resolution(regions)
            logical_candidates = self._dedupe_candidates_by_display(
                self._format_candidates(regions)
            )

            if not logical_candidates:
                logical_candidates = [
                    {
                        "region_id": region_id,
                        "region_name": region_id,
                        "borough": None,
                        "region_ids": [region_id],
                    }
                    for region_id in deduped_input_ids
                ]

            # Note: cached candidate_region_ids reflect the polygon set at cache time.
            # If the display-layer mapping changes (neighborhood gains/loses NTAs),
            # stale aliases are refreshed only when this DB-backed cache entry is replaced.
            # location_aliases currently has no TTL-based expiry.
            if len(logical_candidates) == 1:
                region_ids = self._candidate_region_ids(logical_candidates[0]) or deduped_input_ids
                alias_row.region_boundary_id = str(
                    logical_candidates[0].get("region_id") or region_ids[0]
                )
                alias_row.requires_clarification = False
                alias_row.candidate_region_ids = region_ids if len(region_ids) > 1 else None
            else:
                alias_row.region_boundary_id = None
                alias_row.requires_clarification = True
                alias_row.candidate_region_ids = self._collect_candidate_region_ids(
                    logical_candidates
                )

            self.repository.db.flush()
        except Exception as exc:
            logger.warning(
                "Failed to cache LLM alias '%s': %s",
                normalized,
                str(exc),
                exc_info=True,
            )
            try:
                self.repository.db.rollback()
            except Exception as rollback_exc:
                logger.warning(
                    "Failed to roll back LLM alias cache write for '%s': %s",
                    normalized,
                    str(rollback_exc),
                    exc_info=True,
                )

    @staticmethod
    def _format_candidates(regions: Sequence[object]) -> List[LocationCandidateDisplay]:
        out: List[LocationCandidateDisplay] = []
        for r in regions:
            region_id = getattr(r, "id", None) or getattr(r, "region_id", None)
            region_name = getattr(r, "region_name", None)
            if not region_id or not region_name:
                continue
            borough_value = getattr(r, "parent_region", None)
            if borough_value is None:
                borough_value = getattr(r, "borough", None)
            borough = str(borough_value) if borough_value is not None else None
            display_name_value = getattr(r, "display_name", None)
            display_key_value = getattr(r, "display_key", None)
            out.append(
                {
                    "region_id": str(region_id),
                    "region_name": str(region_name),
                    "borough": borough,
                    "display_name": (
                        str(display_name_value) if display_name_value is not None else None
                    ),
                    "display_key": str(display_key_value)
                    if display_key_value is not None
                    else None,
                    "region_ids": [str(region_id)],
                }
            )
        return sorted(out, key=LocationResolver._candidate_sort_key)

    @staticmethod
    def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[str, str]:
        return (
            str(candidate.get("region_name") or "").strip().lower(),
            str(candidate.get("region_id") or ""),
        )

    @staticmethod
    def _normalize_candidate_name(value: object) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _candidate_region_ids(candidate: Mapping[str, Any]) -> List[str]:
        raw_ids = candidate.get("region_ids")
        if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, (str, bytes)):
            ids = _unique_sorted_region_ids(raw_ids)
            if ids:
                return ids
        region_id = candidate.get("region_id")
        return [str(region_id)] if region_id else []

    @staticmethod
    def _candidate_logical_name(candidate: Mapping[str, Any]) -> str:
        return _logical_region_name(
            region_name=candidate.get("region_name"),
            display_name=candidate.get("display_name"),
        )

    def _expand_regions_for_logical_resolution(
        self,
        regions: Sequence[object],
    ) -> List[object]:
        valid_regions = [
            region
            for region in regions
            if region
            and (getattr(region, "id", None) or getattr(region, "region_id", None))
            and getattr(region, "region_name", None)
        ]
        if len(valid_regions) != 1:
            return list(valid_regions)
        display_key = getattr(valid_regions[0], "display_key", None)
        if not display_key:
            return list(valid_regions)
        if self._region_lookup:
            expanded_infos = self._region_lookup.by_display_key.get(str(display_key), [])
            if expanded_infos:
                return list(expanded_infos)
        expanded_regions = self.repository.get_regions_by_display_key(str(display_key))
        return list(expanded_regions or valid_regions)

    @classmethod
    def _candidate_output(cls, candidate: Mapping[str, Any]) -> LocationCandidateDisplay:
        borough_value = candidate.get("borough")
        output: LocationCandidateDisplay = {
            "region_id": str(candidate.get("region_id") or ""),
            "region_name": str(candidate.get("region_name") or ""),
            "borough": str(borough_value) if borough_value is not None else None,
            "region_ids": cls._candidate_region_ids(candidate),
        }
        if candidate.get("display_name") is not None:
            output["display_name"] = str(candidate.get("display_name") or "")
        if candidate.get("display_key") is not None:
            output["display_key"] = str(candidate.get("display_key") or "")
        return output

    @classmethod
    def _collect_candidate_region_ids(cls, candidates: Sequence[Mapping[str, Any]]) -> List[str]:
        region_ids: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            region_ids.extend(cls._candidate_region_ids(candidate))
        return _unique_sorted_region_ids(region_ids)

    @classmethod
    def _prefer_exact_logical_candidates(
        cls,
        normalized: str,
        candidates: Sequence[dict[str, Any]],
    ) -> List[dict[str, Any]]:
        exact_logical = [
            candidate
            for candidate in candidates
            if cls._normalize_candidate_name(cls._candidate_logical_name(candidate)) == normalized
        ]
        if len(exact_logical) == 1:
            return exact_logical

        exact_raw = [
            candidate
            for candidate in candidates
            if cls._normalize_candidate_name(candidate.get("region_name")) == normalized
        ]
        if len(exact_raw) == 1:
            return exact_raw

        return list(candidates)

    @classmethod
    def effective_region_ids(cls, location_resolution: Optional[ResolvedLocation]) -> List[str]:
        if not location_resolution:
            return []
        if location_resolution.region_ids:
            ids = _unique_sorted_region_ids(location_resolution.region_ids)
            if ids:
                return ids
        if location_resolution.region_id:
            return [str(location_resolution.region_id)]
        if location_resolution.requires_clarification and location_resolution.candidates:
            return cls._collect_candidate_region_ids(location_resolution.candidates)
        return []

    @classmethod
    def _build_result_from_candidates(
        cls,
        candidates: Sequence[Mapping[str, Any]],
        *,
        tier: ResolutionTier,
        confidence: float,
    ) -> ResolvedLocation:
        formatted = [cls._candidate_output(candidate) for candidate in candidates]
        if len(formatted) == 1:
            only = formatted[0]
            return ResolvedLocation.from_region(
                region_id=only["region_id"],
                region_name=cls._candidate_logical_name(only),
                borough=only.get("borough"),
                region_ids=cls._candidate_region_ids(only),
                tier=tier,
                confidence=confidence,
            )
        if len(formatted) >= 2:
            return ResolvedLocation.from_ambiguous(
                candidates=formatted,
                tier=tier,
                confidence=confidence,
            )
        return ResolvedLocation.from_not_found()

    @classmethod
    def _dedupe_candidates_by_display(
        cls,
        candidates: Sequence[Mapping[str, Any]],
    ) -> List[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for candidate in sorted(candidates, key=cls._candidate_sort_key):
            region_id = candidate.get("region_id")
            region_name = candidate.get("region_name")
            if not region_id or not region_name:
                continue

            dedupe_key = str(candidate.get("display_key") or region_id)
            prepared: dict[str, Any] = dict(cls._candidate_output(candidate))
            prepared["region_ids"] = cls._candidate_region_ids(candidate)
            if candidate.get("similarity") is not None:
                try:
                    prepared["similarity"] = float(candidate.get("similarity") or 0.0)
                except (TypeError, ValueError):
                    prepared["similarity"] = 0.0

            if dedupe_key not in seen:
                seen[dedupe_key] = prepared
                continue

            existing = seen[dedupe_key]
            existing["region_ids"] = _unique_sorted_region_ids(
                [
                    *cls._candidate_region_ids(existing),
                    *cls._candidate_region_ids(prepared),
                ]
            )
            if not existing.get("display_name") and prepared.get("display_name"):
                existing["display_name"] = prepared.get("display_name")
            if not existing.get("borough") and prepared.get("borough"):
                existing["borough"] = prepared.get("borough")

            if candidate.get("similarity") is not None:
                try:
                    similarity = float(candidate.get("similarity") or 0.0)
                except (TypeError, ValueError):
                    similarity = 0.0
                try:
                    existing_similarity = float(existing.get("similarity") or 0.0)
                except (TypeError, ValueError):
                    existing_similarity = 0.0
                if similarity > existing_similarity:
                    existing["similarity"] = similarity

        return list(seen.values())
