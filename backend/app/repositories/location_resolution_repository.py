"""Repository for location resolution queries (region_boundaries + location_aliases)."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.location_alias import LocationAlias
from app.models.region_boundary import RegionBoundary

logger = logging.getLogger(__name__)


class LocationResolutionRepository:
    """Encapsulates DB queries needed for location resolution."""

    def __init__(self, db: Session, region_code: str = "nyc") -> None:
        self.db = db
        self.region_code = region_code

    def find_exact_region_by_name(self, normalized: str) -> Optional[RegionBoundary]:
        """Find a region boundary by exact case-insensitive region_name."""
        try:
            region = (
                self.db.query(RegionBoundary)
                .filter(
                    RegionBoundary.region_type == self.region_code,
                    func.lower(RegionBoundary.region_name) == normalized,
                )
                .first()
            )
            return region if isinstance(region, RegionBoundary) else None
        except Exception as exc:
            logger.debug("Exact region lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def find_region_by_alias(self, normalized: str) -> Optional[RegionBoundary]:
        """Resolve an alias to its RegionBoundary (case-insensitive)."""
        try:
            alias_row = (
                self.db.query(LocationAlias)
                .filter(func.lower(LocationAlias.alias) == normalized)
                .first()
            )
            if not isinstance(alias_row, LocationAlias):
                return None

            region = (
                self.db.query(RegionBoundary)
                .filter(
                    RegionBoundary.id == alias_row.region_boundary_id,
                    RegionBoundary.region_type == self.region_code,
                )
                .first()
            )
            return region if isinstance(region, RegionBoundary) else None
        except Exception as exc:
            logger.debug("Alias lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def find_best_fuzzy_region(
        self, normalized: str, *, threshold: float
    ) -> tuple[Optional[RegionBoundary], float]:
        """Find best fuzzy match on region_name using pg_trgm similarity()."""
        try:
            row = self.db.execute(
                text(
                    """
                        SELECT id, similarity(LOWER(region_name), :query) AS sim
                        FROM region_boundaries
                        WHERE region_type = :rtype
                          AND region_name IS NOT NULL
                          AND similarity(LOWER(region_name), :query) > :threshold
                        ORDER BY sim DESC
                        LIMIT 1
                        """
                ),
                {
                    "query": normalized,
                    "rtype": self.region_code,
                    "threshold": threshold,
                },
            ).first()
            if not row:
                return None, 0.0

            region = self.db.get(RegionBoundary, row.id)
            if not isinstance(region, RegionBoundary):
                return None, 0.0
            return region, float(row.sim)
        except Exception as exc:
            # Most commonly: pg_trgm not enabled in the environment.
            logger.debug("Fuzzy region lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None, 0.0
