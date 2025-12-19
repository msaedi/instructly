"""Repository for location resolution queries (region_boundaries + location_aliases)."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

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

    def find_cached_alias(
        self, normalized: str, *, source: Optional[str] = None
    ) -> Optional[LocationAlias]:
        """
        Find a cached alias row regardless of trust model (excluding deprecated).

        Used for Tier 5 (LLM) caching, where we want to avoid repeat LLM calls even
        while the alias is still pending_review.
        """
        try:
            query = self.db.query(LocationAlias).filter(
                LocationAlias.city_id == self.city_id,
                func.lower(LocationAlias.alias_normalized) == normalized,
                LocationAlias.status != "deprecated",
            )
            if source:
                query = query.filter(LocationAlias.source == source)
            alias_row = query.first()
            return alias_row if isinstance(alias_row, LocationAlias) else None
        except Exception as exc:
            logger.debug("Cached alias lookup failed for '%s': %s", normalized, str(exc))
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

    def list_regions(self, *, limit: int = 2000) -> list[RegionBoundary]:
        """List RegionBoundary rows for this region_code (best-effort)."""
        try:
            rows = (
                self.db.query(RegionBoundary)
                .filter(
                    RegionBoundary.region_type == self.region_code,
                    RegionBoundary.region_name.isnot(None),
                )
                .order_by(
                    func.coalesce(RegionBoundary.parent_region, "").asc(),
                    func.coalesce(RegionBoundary.region_name, "").asc(),
                    RegionBoundary.id.asc(),
                )
                .limit(int(limit))
                .all()
            )
            return [r for r in rows if isinstance(r, RegionBoundary)]
        except Exception as exc:
            logger.debug("Region list failed: %s", str(exc))
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

    def get_best_fuzzy_score(self, normalized: str) -> float:
        """
        Get the best fuzzy similarity score for a query, without threshold filtering.

        Used to gate whether embedding tier should be attempted - if the query has
        extremely low lexical similarity to all region names, it's likely nonsense
        and embedding tier would produce false positives.
        """
        try:
            row = self.db.execute(
                text(
                    """
                    SELECT MAX(similarity(LOWER(region_name), :query)) AS max_sim
                    FROM region_boundaries
                    WHERE region_type = :rtype
                      AND region_name IS NOT NULL
                    """
                ),
                {"query": normalized, "rtype": self.region_code},
            ).first()
            return float(row.max_sim or 0.0) if row else 0.0
        except Exception as exc:
            logger.debug("Best fuzzy score lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return 0.0

    def list_fuzzy_region_names(self, normalized: str, *, limit: int = 5) -> list[str]:
        """
        Return top fuzzy region_name candidates ordered by similarity.

        Uses pg_trgm similarity() without threshold filtering to support Tier 5 prompts.
        """
        normalized = " ".join(str(normalized or "").strip().lower().split())
        if not normalized:
            return []

        try:
            rows = self.db.execute(
                text(
                    """
                    SELECT region_name, similarity(LOWER(region_name), :query) AS sim
                    FROM region_boundaries
                    WHERE region_type = :rtype
                      AND region_name IS NOT NULL
                    ORDER BY sim DESC
                    LIMIT :limit
                    """
                ),
                {"query": normalized, "rtype": self.region_code, "limit": int(limit)},
            ).fetchall()
        except Exception as exc:
            logger.debug("Fuzzy candidate lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return []

        out: list[str] = []
        seen: set[str] = set()
        for row in rows or []:
            name = getattr(row, "region_name", None)
            if not name and row:
                try:
                    name = row[0]
                except Exception:
                    name = None
            if not name:
                continue
            key = str(name).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(str(name).strip())
        return out

    def find_regions_by_name_fragment(self, fragment: str) -> list[RegionBoundary]:
        """
        Find regions whose region_name contains the given fragment (case-insensitive).

        Used to bridge differences between alias labels (e.g., "Upper East Side") and
        canonical region_boundaries names (e.g., "Upper East Side-Carnegie Hill").
        """
        normalized = " ".join(str(fragment).strip().lower().split())
        if not normalized:
            return []

        try:
            regions = (
                self.db.query(RegionBoundary)
                .filter(
                    RegionBoundary.region_type == self.region_code,
                    RegionBoundary.region_name.isnot(None),
                    func.lower(RegionBoundary.region_name).like(f"%{normalized}%"),
                )
                .all()
            )
            return [r for r in regions if isinstance(r, RegionBoundary)]
        except Exception as exc:
            logger.debug("Region fragment lookup failed for '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return []

    def list_region_names(self) -> list[str]:
        """List region_boundaries.region_name values for this region_code (for LLM prompts)."""
        try:
            rows = self.db.execute(
                text(
                    """
                    SELECT region_name
                    FROM region_boundaries
                    WHERE region_type = :rtype
                      AND region_name IS NOT NULL
                    ORDER BY region_name
                    """
                ),
                {"rtype": self.region_code},
            ).fetchall()
            return [str(r[0]) for r in rows if r and r[0]]
        except Exception as exc:
            logger.debug("Region name listing failed: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return []

    def has_region_name_embeddings(self) -> bool:
        """Return True if `region_boundaries.name_embedding` has any populated rows."""
        try:
            row = self.db.execute(
                text(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM region_boundaries
                        WHERE region_type = :rtype
                          AND name_embedding IS NOT NULL
                        LIMIT 1
                    ) AS has_embeddings
                    """
                ),
                {"rtype": self.region_code},
            ).first()
            return bool(getattr(row, "has_embeddings", False)) if row else False
        except Exception as exc:
            logger.debug("Embedding availability check failed: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def find_regions_by_name_embedding(
        self, embedding: List[float], *, limit: int = 5
    ) -> List[Tuple[RegionBoundary, float]]:
        """
        Find regions by pgvector similarity on `region_boundaries.name_embedding`.

        Returns ordered pairs of (RegionBoundary, similarity) where similarity is normalized to [0..1].
        """
        if not embedding:
            return []

        try:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            rows = self.db.execute(
                text(
                    """
                    SELECT
                        id,
                        GREATEST(0, 1 - ((name_embedding <=> CAST(:embedding AS vector)) / 2)) AS similarity
                    FROM region_boundaries
                    WHERE region_type = :rtype
                      AND name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                    """
                ),
                {"embedding": embedding_str, "rtype": self.region_code, "limit": int(limit)},
            ).fetchall()

            if not rows:
                return []

            ids = [str(r.id) for r in rows if getattr(r, "id", None)]
            regions = self.get_regions_by_ids(ids)
            by_id = {str(r.id): r for r in regions if getattr(r, "id", None)}

            ordered: List[Tuple[RegionBoundary, float]] = []
            for r in rows:
                region = by_id.get(str(r.id))
                if not region:
                    continue
                try:
                    ordered.append((region, float(r.similarity or 0.0)))
                except Exception:
                    ordered.append((region, 0.0))
            return ordered
        except Exception as exc:
            logger.debug("Embedding region lookup failed: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return []
