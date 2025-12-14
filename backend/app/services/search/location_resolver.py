"""
Location resolver for NL search.

Phase 1 supports a 3-tier pipeline:
1) Exact match on `region_boundaries.region_name`
2) Alias lookup in `location_aliases` (trust + ambiguity model)
3) Fuzzy match via pg_trgm `similarity()` on `region_boundaries.region_name`

Notes:
- `region_boundaries` is the source of truth for neighborhood names.
- Borough inputs are treated as a parent_region filter (no need for a borough boundary row).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import List, Optional, Sequence, TypedDict

from sqlalchemy.orm import Session

from app.models.location_alias import NYC_CITY_ID
from app.models.region_boundary import RegionBoundary
from app.repositories.location_resolution_repository import LocationResolutionRepository
from app.repositories.unresolved_location_query_repository import (
    UnresolvedLocationQueryRepository,
)

logger = logging.getLogger(__name__)


class ResolutionTier(Enum):
    EXACT = 1
    ALIAS = 2
    FUZZY = 3
    EMBEDDING = 4  # Future
    LLM = 5  # Future
    NOT_FOUND = 0


class LocationCandidate(TypedDict):
    region_id: str
    region_name: str
    borough: str | None


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

    # Ambiguous data (if requires_clarification=True)
    candidates: Optional[List[LocationCandidate]] = None

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
        tier: ResolutionTier,
        confidence: float,
    ) -> "ResolvedLocation":
        return cls(
            resolved=True,
            region_id=region_id,
            region_name=region_name,
            borough=borough,
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
        candidates: List[LocationCandidate],
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

    Tier 1-3 implemented:
    - exact
    - alias (trust + ambiguity)
    - fuzzy
    """

    # Thresholds (calibrate via eval harness)
    FUZZY_THRESHOLD = 0.4

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
    ) -> None:
        self.region_code = region_code
        self.city_id = city_id
        self.repository = repository or LocationResolutionRepository(
            db, region_code=region_code, city_id=city_id
        )
        self.unresolved_repository = unresolved_repository or UnresolvedLocationQueryRepository(
            db, city_id=city_id
        )

    def resolve(
        self,
        location_text: str,
        *,
        original_query: Optional[str] = None,
        track_unresolved: bool = False,
    ) -> ResolvedLocation:
        """
        Resolve a user-entered location string to a region boundary or borough.

        If `track_unresolved=True`, unresolved location texts are persisted to
        `unresolved_location_queries` for later analysis.
        """
        if not location_text:
            return ResolvedLocation.from_not_found()

        normalized = self._normalize(location_text)
        if not normalized or len(normalized) < 2:
            return ResolvedLocation.from_not_found()

        # Tier 0: Borough aliases (no DB dependency)
        borough_key = self._BOROUGH_ALIASES.get(normalized)
        if borough_key:
            return ResolvedLocation.from_borough(
                borough=self._BOROUGH_CANONICAL[borough_key],
                tier=ResolutionTier.ALIAS,
                confidence=1.0,
            )

        # Tier 1: Exact match (includes borough names)
        exact = self._tier1_exact_match(normalized)
        if exact.resolved:
            return exact

        # Tier 2: Alias lookup (trust + ambiguity)
        alias_result = self._tier2_alias_lookup(normalized)
        if alias_result.resolved or alias_result.requires_clarification:
            return alias_result

        # Tier 3: Fuzzy match (pg_trgm similarity)
        fuzzy = self._tier3_fuzzy_match(normalized)
        if fuzzy.resolved:
            return fuzzy

        if track_unresolved:
            self.unresolved_repository.track_unresolved(
                normalized, original_query=original_query or location_text
            )
            logger.info("Tracked unresolved location '%s' (city_id=%s)", normalized, self.city_id)

        return ResolvedLocation.from_not_found()

    def _normalize(self, text_value: str) -> str:
        normalized = " ".join(str(text_value).lower().strip().split())
        wrappers = ("near ", "by ", "in ", "around ", "close to ", "at ")
        for wrapper in wrappers:
            if normalized.startswith(wrapper):
                normalized = normalized[len(wrapper) :]
        if normalized.endswith(" area"):
            normalized = normalized[:-5]
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
            return ResolvedLocation.from_region(
                region_id=region.id,
                region_name=region.region_name,
                borough=getattr(region, "parent_region", None),
                tier=ResolutionTier.EXACT,
                confidence=1.0,
            )

        return ResolvedLocation.from_not_found()

    def _tier2_alias_lookup(self, normalized: str) -> ResolvedLocation:
        alias_row = self.repository.find_trusted_alias(normalized)
        if not alias_row:
            return ResolvedLocation.from_not_found()

        self.repository.increment_alias_user_count(alias_row)

        if alias_row.is_ambiguous and alias_row.candidate_region_ids:
            regions = self.repository.get_regions_by_ids(list(alias_row.candidate_region_ids))
            candidates = self._format_candidates(regions)
            if len(candidates) >= 2:
                return ResolvedLocation.from_ambiguous(
                    candidates=candidates,
                    tier=ResolutionTier.ALIAS,
                    confidence=float(alias_row.confidence or 1.0),
                )

        if alias_row.is_resolved and alias_row.region_boundary_id:
            region = self.repository.get_region_by_id(str(alias_row.region_boundary_id))
            if region and getattr(region, "id", None) and getattr(region, "region_name", None):
                return ResolvedLocation.from_region(
                    region_id=region.id,
                    region_name=region.region_name,
                    borough=getattr(region, "parent_region", None),
                    tier=ResolutionTier.ALIAS,
                    confidence=float(alias_row.confidence or 1.0),
                )

        return ResolvedLocation.from_not_found()

    def _tier3_fuzzy_match(self, normalized: str) -> ResolvedLocation:
        region, similarity = self.repository.find_best_fuzzy_region(
            normalized, threshold=self.FUZZY_THRESHOLD
        )
        if region and getattr(region, "id", None) and getattr(region, "region_name", None):
            return ResolvedLocation.from_region(
                region_id=region.id,
                region_name=region.region_name,
                borough=getattr(region, "parent_region", None),
                tier=ResolutionTier.FUZZY,
                confidence=float(similarity or 0.0),
            )
        return ResolvedLocation.from_not_found()

    @staticmethod
    def _format_candidates(regions: Sequence[RegionBoundary]) -> List[LocationCandidate]:
        out: List[LocationCandidate] = []
        for r in regions:
            if not getattr(r, "id", None) or not getattr(r, "region_name", None):
                continue
            out.append(
                {
                    "region_id": r.id,
                    "region_name": r.region_name,
                    "borough": getattr(r, "parent_region", None),
                }
            )
        return out
