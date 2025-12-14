"""Repository for location resolution queries (region_boundaries + location_aliases)."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.models.location_alias import NYC_CITY_ID, LocationAlias
from app.models.region_boundary import RegionBoundary

logger = logging.getLogger(__name__)


class LocationResolutionRepository:
    """Encapsulates DB queries needed for location resolution."""

    # Trust model thresholds (for pending_review)
    PENDING_CONFIDENCE_THRESHOLD = 0.9
    PENDING_USER_COUNT_THRESHOLD = 5

    def __init__(
        self,
        db: Session,
        *,
        region_code: str = "nyc",
        city_id: str = NYC_CITY_ID,
    ) -> None:
        self.db = db
        self.region_code = region_code
        self.city_id = city_id

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

    def find_trusted_alias(self, normalized: str) -> Optional[LocationAlias]:
        """
        Find a trusted LocationAlias for this city_id.

        Trust model:
        - status='active'
        - OR status='pending_review' with high confidence and sufficient usage
        - Never use status='deprecated'
        """
        try:
            alias_row = (
                self.db.query(LocationAlias)
                .filter(
                    LocationAlias.city_id == self.city_id,
                    func.lower(LocationAlias.alias_normalized) == normalized,
                    LocationAlias.status != "deprecated",
                    or_(
                        LocationAlias.status == "active",
                        and_(
                            LocationAlias.status == "pending_review",
                            LocationAlias.confidence >= self.PENDING_CONFIDENCE_THRESHOLD,
                            LocationAlias.user_count >= self.PENDING_USER_COUNT_THRESHOLD,
                        ),
                    ),
                )
                .first()
            )
            return alias_row if isinstance(alias_row, LocationAlias) else None
        except Exception as exc:
            logger.debug("Trusted alias lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def increment_alias_user_count(self, alias_row: LocationAlias) -> None:
        """Increment user_count for an alias (best-effort)."""
        try:
            alias_row.user_count = int(alias_row.user_count or 0) + 1
            self.db.flush()
        except Exception as exc:
            logger.debug(
                "Failed to increment alias user_count for '%s': %s",
                alias_row.alias_normalized,
                str(exc),
            )
            try:
                self.db.rollback()
            except Exception:
                pass

    def get_region_by_id(self, region_id: str) -> Optional[RegionBoundary]:
        """Fetch a RegionBoundary by id within this region_code."""
        try:
            region = (
                self.db.query(RegionBoundary)
                .filter(
                    RegionBoundary.id == region_id,
                    RegionBoundary.region_type == self.region_code,
                )
                .first()
            )
            return region if isinstance(region, RegionBoundary) else None
        except Exception as exc:
            logger.debug("Region lookup failed for '%s': %s", region_id, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def get_regions_by_ids(self, region_ids: list[str]) -> list[RegionBoundary]:
        """Fetch RegionBoundary rows by ids within this region_code."""
        if not region_ids:
            return []
        try:
            regions = (
                self.db.query(RegionBoundary)
                .filter(
                    RegionBoundary.region_type == self.region_code,
                    RegionBoundary.id.in_(region_ids),
                )
                .all()
            )
            return [r for r in regions if isinstance(r, RegionBoundary)]
        except Exception as exc:
            logger.debug("Bulk region lookup failed: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return []

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

            region = self.get_region_by_id(str(row.id))
            if not isinstance(region, RegionBoundary):
                return None, 0.0
            return region, float(row.sim or 0.0)
        except Exception as exc:
            # Most commonly: pg_trgm not enabled in the environment.
            logger.debug("Fuzzy region lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None, 0.0
