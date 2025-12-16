"""Repository for unresolved location query tracking."""

from __future__ import annotations

import logging
from typing import Any, Optional

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

    def record_click(
        self,
        query_normalized: str,
        *,
        region_boundary_id: str,
        original_query: Optional[str] = None,
        max_samples: int = 10,
    ) -> None:
        """
        Record a click outcome for an unresolved location query.

        This is a best-effort signal for the self-learning alias loop.
        """
        normalized = " ".join(str(query_normalized).strip().lower().split())
        if not normalized or not region_boundary_id:
            return

        try:
            row = (
                self.db.query(UnresolvedLocationQuery)
                .filter(
                    UnresolvedLocationQuery.city_id == self.city_id,
                    UnresolvedLocationQuery.query_normalized == normalized,
                )
                .first()
            )
            existing = row if isinstance(row, UnresolvedLocationQuery) else None

            if not existing:
                existing = UnresolvedLocationQuery(
                    id=generate_ulid(),
                    city_id=self.city_id,
                    query_normalized=normalized,
                    sample_original_queries=[original_query] if original_query else [],
                    search_count=1,
                    unique_user_count=1,
                    click_region_counts={},
                    click_count=0,
                    status="pending",
                )
                self.db.add(existing)
                self.db.flush()

            existing.click_count = int(existing.click_count or 0) + 1
            existing.last_clicked_at = func.now()

            counts: dict[str, Any] = dict(existing.click_region_counts or {})
            counts[region_boundary_id] = int(counts.get(region_boundary_id, 0) or 0) + 1
            existing.click_region_counts = counts

            if original_query:
                samples = list(existing.sample_original_queries or [])
                if original_query not in samples and len(samples) < max_samples:
                    samples.append(original_query)
                    existing.sample_original_queries = samples

            self.db.flush()
        except Exception as exc:
            logger.debug(
                "Failed to record click for unresolved location '%s': %s", normalized, str(exc)
            )
            try:
                self.db.rollback()
            except Exception:
                pass

    def list_pending(self, *, limit: int = 50) -> list[UnresolvedLocationQuery]:
        """List pending unresolved queries for admin review."""
        try:
            rows = (
                self.db.query(UnresolvedLocationQuery)
                .filter(UnresolvedLocationQuery.city_id == self.city_id)
                .filter(UnresolvedLocationQuery.status == "pending")
                .order_by(UnresolvedLocationQuery.search_count.desc())
                .limit(limit)
                .all()
            )
            return [r for r in rows if isinstance(r, UnresolvedLocationQuery)]
        except Exception as exc:
            logger.debug("Failed to list pending unresolved queries: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return []

    def get_by_normalized(self, query_normalized: str) -> Optional[UnresolvedLocationQuery]:
        """Fetch a single unresolved query row by normalized text."""
        normalized = " ".join(str(query_normalized).strip().lower().split())
        if not normalized:
            return None

        try:
            row = (
                self.db.query(UnresolvedLocationQuery)
                .filter(
                    UnresolvedLocationQuery.city_id == self.city_id,
                    UnresolvedLocationQuery.query_normalized == normalized,
                )
                .first()
            )
            return row if isinstance(row, UnresolvedLocationQuery) else None
        except Exception as exc:
            logger.debug("Failed to fetch unresolved query '%s': %s", normalized, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def list_pending_with_evidence(
        self,
        *,
        min_clicks: int,
        min_searches: int,
        limit: int,
    ) -> list[UnresolvedLocationQuery]:
        """List pending unresolved queries with enough evidence to learn from."""
        try:
            rows = (
                self.db.query(UnresolvedLocationQuery)
                .filter(
                    UnresolvedLocationQuery.city_id == self.city_id,
                    UnresolvedLocationQuery.status == "pending",
                    UnresolvedLocationQuery.click_count >= int(min_clicks),
                    UnresolvedLocationQuery.search_count >= int(min_searches),
                )
                .order_by(UnresolvedLocationQuery.click_count.desc())
                .limit(int(limit))
                .all()
            )
            return [r for r in rows if isinstance(r, UnresolvedLocationQuery)]
        except Exception as exc:
            logger.debug("Failed to list learnable unresolved queries: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return []

    def mark_manual_review(self, row: UnresolvedLocationQuery) -> None:
        """Mark an unresolved query row as needing manual review (best-effort)."""
        try:
            row.status = "manual_review"
            self.db.flush()
        except Exception as exc:
            logger.debug("Failed to mark unresolved query manual_review: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass

    def set_status(self, query_normalized: str, *, status: str) -> bool:
        """Update status for an unresolved query row (best-effort)."""
        row = self.get_by_normalized(query_normalized)
        if not row:
            return False
        try:
            row.status = str(status)
            self.db.flush()
            return True
        except Exception as exc:
            logger.debug(
                "Failed to set unresolved query '%s' status=%s: %s",
                query_normalized,
                status,
                str(exc),
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def mark_resolved(
        self, query_normalized: str, *, region_boundary_id: Optional[str] = None
    ) -> bool:
        """Mark an unresolved query as handled via admin action (best-effort)."""
        row = self.get_by_normalized(query_normalized)
        if not row:
            return False
        try:
            row.status = "manual_review"
            if region_boundary_id:
                row.resolved_region_boundary_id = str(region_boundary_id)
                row.resolved_at = func.now()
            row.reviewed = True
            row.reviewed_at = func.now()
            self.db.flush()
            return True
        except Exception as exc:
            logger.debug("Failed to mark unresolved query resolved: %s", str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return False
