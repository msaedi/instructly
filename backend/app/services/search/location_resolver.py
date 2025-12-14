"""
Location resolver for NL search.

Resolves user-entered location text (e.g., "lower east side", "bk", "les") to
the canonical `region_boundaries` rows.

Resolution order:
1. Exact match on `region_boundaries.region_name` (case-insensitive)
2. Alias lookup in `location_aliases`
3. Fuzzy match via pg_trgm `similarity()` on `region_boundaries.region_name`

Notes:
- `region_boundaries` is the source of truth for neighborhood names.
- Borough inputs are treated as a parent_region filter (no need for a borough boundary row).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.region_boundary import RegionBoundary
from app.repositories.location_resolution_repository import LocationResolutionRepository


@dataclass(frozen=True)
class ResolvedLocation:
    """Represents a resolved location for filtering/ranking."""

    kind: str  # "region" | "borough" | "none"
    method: str  # "exact" | "alias" | "fuzzy" | "none"

    region: Optional[RegionBoundary] = None
    borough_name: Optional[str] = None
    similarity: Optional[float] = None


class LocationResolver:
    """Resolves user location input to `region_boundaries` or a borough filter."""

    FUZZY_THRESHOLD = 0.3

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

    # Small built-in safety net so common abbreviations work even if location_aliases
    # hasn't been seeded yet.
    _NEIGHBORHOOD_ABBREV_FALLBACK = {
        "les": "lower east side",
        "uws": "upper west side",
        "ues": "upper east side",
        "fidi": "financial district",
        "lic": "long island city",
        "wburg": "williamsburg",
        "bedstuy": "bedford-stuyvesant",
        "bed stuy": "bedford-stuyvesant",
        "bed-stuy": "bedford-stuyvesant",
    }

    def __init__(
        self,
        db: Session,
        region_code: str = "nyc",
        repository: Optional[LocationResolutionRepository] = None,
    ) -> None:
        self.region_code = region_code
        self.repository = repository or LocationResolutionRepository(db, region_code=region_code)

    def resolve(self, location_text: str) -> ResolvedLocation:
        if not location_text:
            return ResolvedLocation(kind="none", method="none")

        normalized = " ".join(location_text.strip().lower().split())
        if not normalized:
            return ResolvedLocation(kind="none", method="none")

        # Borough aliases (no DB dependency)
        borough_key = self._BOROUGH_ALIASES.get(normalized)
        if borough_key:
            return ResolvedLocation(
                kind="borough",
                method="alias",
                borough_name=self._BOROUGH_CANONICAL[borough_key],
            )

        # Built-in neighborhood abbreviations (tries exact match on region_boundaries)
        fallback = self._NEIGHBORHOOD_ABBREV_FALLBACK.get(normalized)
        if fallback:
            region = self.repository.find_exact_region_by_name(fallback)
            if region:
                return ResolvedLocation(kind="region", method="alias", region=region)

        # Exact match on region_boundaries.region_name
        region = self.repository.find_exact_region_by_name(normalized)
        if region:
            borough_name = self._BOROUGH_CANONICAL.get(normalized)
            if borough_name:
                return ResolvedLocation(kind="borough", method="exact", borough_name=borough_name)
            return ResolvedLocation(kind="region", method="exact", region=region)

        # Borough names even if there isn't a dedicated region boundary row
        borough_name = self._BOROUGH_CANONICAL.get(normalized)
        if borough_name:
            return ResolvedLocation(kind="borough", method="exact", borough_name=borough_name)

        # Alias lookup (location_aliases -> region_boundaries)
        region = self.repository.find_region_by_alias(normalized)
        if region:
            borough_name = (
                self._BOROUGH_CANONICAL.get(region.region_name.lower())
                if region.region_name
                else None
            )
            if borough_name:
                return ResolvedLocation(
                    kind="borough", method="alias", borough_name=borough_name, region=region
                )
            return ResolvedLocation(kind="region", method="alias", region=region)

        # Fuzzy match (pg_trgm similarity)
        region, similarity = self.repository.find_best_fuzzy_region(
            normalized, threshold=self.FUZZY_THRESHOLD
        )
        if region:
            return ResolvedLocation(
                kind="region",
                method="fuzzy",
                region=region,
                similarity=similarity,
            )

        return ResolvedLocation(kind="none", method="none")
