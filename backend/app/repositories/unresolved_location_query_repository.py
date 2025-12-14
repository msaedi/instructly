"""Repository for unresolved location query tracking."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.location_alias import NYC_CITY_ID
from app.models.unresolved_location_query import UnresolvedLocationQuery

logger = logging.getLogger(__name__)


class UnresolvedLocationQueryRepository:
    """Encapsulates DB writes for tracking unresolved location queries."""

    def __init__(self, db: Session, *, city_id: str = NYC_CITY_ID) -> None:
        self.db = db
        self.city_id = city_id

    def track_unresolved(
        self,
        query_normalized: str,
        *,
        original_query: Optional[str] = None,
        max_samples: int = 10,
    ) -> None:
        """
        Upsert an unresolved location query row.

        Note: `unique_user_count` is incremented per call for now (no per-user identity available).
        """
        if not query_normalized:
            return

        try:
            row = (
                self.db.query(UnresolvedLocationQuery)
                .filter(
                    UnresolvedLocationQuery.city_id == self.city_id,
                    UnresolvedLocationQuery.query_normalized == query_normalized,
                )
                .first()
            )
            existing = row if isinstance(row, UnresolvedLocationQuery) else None

            if existing:
                existing.search_count = int(existing.search_count or 0) + 1
                existing.unique_user_count = int(existing.unique_user_count or 0) + 1
                existing.last_seen_at = func.now()

                if original_query:
                    samples = list(existing.sample_original_queries or [])
                    if original_query not in samples and len(samples) < max_samples:
                        samples.append(original_query)
                        existing.sample_original_queries = samples
            else:
                self.db.add(
                    UnresolvedLocationQuery(
                        id=generate_ulid(),
                        city_id=self.city_id,
                        query_normalized=query_normalized,
                        sample_original_queries=[original_query] if original_query else [],
                        search_count=1,
                        unique_user_count=1,
                    )
                )

            self.db.flush()
        except Exception as exc:
            logger.debug("Failed to track unresolved location '%s': %s", query_normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
