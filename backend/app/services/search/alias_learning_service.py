"""Self-learning service for location aliases.

Learns mappings from unresolved location queries to region_boundaries based on
user click behavior. The learned mapping is persisted into `location_aliases`
so future searches can resolve immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.location_alias import NYC_CITY_ID, LocationAlias
from app.models.unresolved_location_query import UnresolvedLocationQuery
from app.repositories.location_alias_repository import LocationAliasRepository
from app.repositories.location_resolution_repository import LocationResolutionRepository
from app.repositories.unresolved_location_query_repository import UnresolvedLocationQueryRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LearnedAlias:
    alias_normalized: str
    region_boundary_id: str
    confidence: float
    status: str
    confirmations: int


class AliasLearningService:
    """Learns `location_aliases` rows from click behavior."""

    # Minimum evidence before we create a learned alias
    MIN_CLICKS = 3
    MIN_CONFIDENCE = 0.7
    MIN_SEARCHES = 5

    # Auto-activate stronger mappings; otherwise create as pending_review
    AUTO_ACTIVATE_CONFIDENCE = 0.9
    AUTO_ACTIVATE_CLICKS = 5

    def __init__(
        self,
        db: Session,
        *,
        city_id: str = NYC_CITY_ID,
        region_code: str = "nyc",
    ) -> None:
        self.db = db
        self.city_id = city_id
        self.region_code = region_code
        self.unresolved_repo = UnresolvedLocationQueryRepository(db, city_id=city_id)
        self.location_resolution_repo = LocationResolutionRepository(
            db, region_code=region_code, city_id=city_id
        )
        self.location_alias_repo = LocationAliasRepository(db, city_id=city_id)

    def maybe_learn_from_query(self, query_normalized: str) -> Optional[LearnedAlias]:
        normalized = " ".join(str(query_normalized).strip().lower().split())
        if not normalized:
            return None

        row = self.unresolved_repo.get_by_normalized(normalized)
        if not row:
            return None

        return self._learn_from_row(row)

    def process_pending(self, *, limit: int = 250) -> list[LearnedAlias]:
        """Process pending unresolved queries that have click evidence."""
        rows = self.unresolved_repo.list_pending_with_evidence(
            min_clicks=self.MIN_CLICKS,
            min_searches=self.MIN_SEARCHES,
            limit=limit,
        )

        learned: list[LearnedAlias] = []
        for row in rows:
            alias = self._learn_from_row(row)
            if alias:
                learned.append(alias)
        return learned

    def _learn_from_row(self, row: UnresolvedLocationQuery) -> Optional[LearnedAlias]:
        if row.status != "pending":
            return None

        counts = row.click_region_counts or {}
        if not isinstance(counts, dict) or not counts:
            return None

        total_clicks = int(row.click_count or 0)
        if total_clicks <= 0:
            total_clicks = sum(int(v or 0) for v in counts.values() if isinstance(v, (int, float)))
        if total_clicks < self.MIN_CLICKS:
            return None

        top_region_id = None
        top_count = 0
        for region_id, value in counts.items():
            if not region_id:
                continue
            try:
                count = int(value or 0)
            except Exception:
                continue
            if count > top_count:
                top_region_id = str(region_id)
                top_count = count

        if not top_region_id or top_count <= 0:
            return None

        confidence = float(top_count) / float(total_clicks)
        if confidence < self.MIN_CONFIDENCE:
            return None

        if int(row.search_count or 0) < self.MIN_SEARCHES:
            return None

        # Validate region exists in this region_code.
        region = self.location_resolution_repo.get_region_by_id(top_region_id)
        if not region:
            return None

        # Do not override existing aliases (manual/llm/etc).
        existing_alias = self.location_resolution_repo.find_cached_alias(row.query_normalized)
        if existing_alias:
            # Mark for manual review instead of overriding.
            self.unresolved_repo.mark_manual_review(row)
            return None

        status = (
            "active"
            if confidence >= self.AUTO_ACTIVATE_CONFIDENCE
            and top_count >= self.AUTO_ACTIVATE_CLICKS
            else "pending_review"
        )

        alias = LocationAlias(
            id=generate_ulid(),
            city_id=self.city_id,
            alias_normalized=row.query_normalized,
            region_boundary_id=region.id,
            requires_clarification=False,
            candidate_region_ids=None,
            status=status,
            confidence=confidence,
            source="user_learning",
            user_count=top_count,
            alias_type="landmark",
        )

        row.status = "learned"
        row.resolved_region_boundary_id = region.id
        row.resolved_at = func.now()

        if not self.location_alias_repo.add(alias):
            return None

        learned = LearnedAlias(
            alias_normalized=row.query_normalized,
            region_boundary_id=str(region.id),
            confidence=confidence,
            status=status,
            confirmations=top_count,
        )
        logger.info(
            "Learned location alias '%s' -> '%s' (confidence=%.2f, confirmations=%d, status=%s)",
            learned.alias_normalized,
            region.region_name,
            learned.confidence,
            learned.confirmations,
            learned.status,
        )
        return learned
