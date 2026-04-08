"""Candidate tracking analytics and service supply joins."""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.sql.expression import literal

from ...models.search_event import SearchEvent, SearchEventCandidate
from ...models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from ...models.subcategory import ServiceSubcategory
from .mixin_base import SearchAnalyticsRepositoryMixinBase
from .types import (
    CandidateServiceQueryData,
    CandidateSummaryData,
    CategoryTrendData,
    TopServiceData,
)


class CandidateAnalyticsMixin(SearchAnalyticsRepositoryMixinBase):
    """Candidate tracking, category rollups, and service supply metrics."""

    def get_candidate_summary(
        self, start_datetime: datetime, end_datetime: datetime
    ) -> CandidateSummaryData:
        """
        Get summary statistics for search candidates.

        Args:
            start_datetime: Start of time range
            end_datetime: End of time range

        Returns:
            Candidate summary data
        """
        date_filter = and_(
            SearchEventCandidate.created_at >= start_datetime,
            SearchEventCandidate.created_at <= end_datetime,
        )

        total_candidates = (
            self.db.query(func.count(SearchEventCandidate.id)).filter(date_filter).scalar() or 0
        )

        events_with_candidates = (
            self.db.query(func.count(func.distinct(SearchEventCandidate.search_event_id)))
            .filter(date_filter)
            .scalar()
            or 0
        )

        zero_result_events_with_candidates = (
            self.db.query(func.count(func.distinct(SearchEventCandidate.search_event_id)))
            .join(SearchEvent, SearchEvent.id == SearchEventCandidate.search_event_id)
            .filter(date_filter, SearchEvent.results_count == 0)
            .scalar()
            or 0
        )

        # Source breakdown
        rows = (
            self.db.query(SearchEventCandidate.source, func.count(SearchEventCandidate.id))
            .filter(date_filter)
            .group_by(SearchEventCandidate.source)
            .all()
        )
        source_breakdown = {r[0] or "unknown": r[1] for r in rows}

        return CandidateSummaryData(
            total_candidates=total_candidates,
            events_with_candidates=events_with_candidates,
            zero_result_events_with_candidates=zero_result_events_with_candidates,
            source_breakdown=source_breakdown,
        )

    def get_candidate_category_trends(
        self, start_datetime: datetime, end_datetime: datetime
    ) -> List[CategoryTrendData]:
        """
        Get candidate counts by date and category.

        Note: Falls back to a date-only aggregation with "unknown" categories
        when the richer join path fails or returns no rows. Older
        search_event_candidates rows may reference services that no longer
        resolve through the catalog tables, and this keeps those events in the
        trend analysis instead of dropping them entirely.

        Args:
            start_datetime: Start of time range
            end_datetime: End of time range

        Returns:
            List of category trend data
        """
        date_filter = and_(
            SearchEventCandidate.created_at >= start_datetime,
            SearchEventCandidate.created_at <= end_datetime,
        )

        date_expr = func.date(SearchEventCandidate.created_at)
        category_expr = func.coalesce(ServiceCategory.name, literal("unknown"))

        try:
            rows = (
                self.db.query(
                    date_expr.label("date"),
                    category_expr.label("category"),
                    func.count(SearchEventCandidate.id).label("count"),
                )
                .select_from(SearchEventCandidate)
                .outerjoin(
                    ServiceCatalog,
                    ServiceCatalog.id == SearchEventCandidate.service_catalog_id,
                )
                .outerjoin(
                    ServiceSubcategory, ServiceSubcategory.id == ServiceCatalog.subcategory_id
                )
                .outerjoin(ServiceCategory, ServiceCategory.id == ServiceSubcategory.category_id)
                .filter(date_filter)
                .group_by(date_expr, category_expr)
                .order_by(date_expr)
                .all()
            )
        except Exception:
            rows = []

        # Fallback if query failed
        if not rows:
            rows = (
                self.db.query(
                    func.date(SearchEventCandidate.created_at).label("date"),
                    literal("unknown").label("category"),
                    func.count(SearchEventCandidate.id).label("count"),
                )
                .filter(date_filter)
                .group_by(func.date(SearchEventCandidate.created_at))
                .order_by(func.date(SearchEventCandidate.created_at))
                .all()
            )

        return [CategoryTrendData(date=r.date, category=r.category, count=r.count) for r in rows]

    def get_candidate_top_services(
        self, start_datetime: datetime, end_datetime: datetime, limit: int = 20
    ) -> List[TopServiceData]:
        """
        Get top services by candidate count.

        Args:
            start_datetime: Start of time range
            end_datetime: End of time range
            limit: Maximum results to return

        Returns:
            List of top service data
        """
        date_filter = and_(
            SearchEventCandidate.created_at >= start_datetime,
            SearchEventCandidate.created_at <= end_datetime,
        )

        rows = (
            self.db.query(
                SearchEventCandidate.service_catalog_id,
                ServiceCatalog.name.label("service_name"),
                ServiceCategory.name.label("category_name"),
                func.count(SearchEventCandidate.id).label("candidate_count"),
                func.avg(func.coalesce(SearchEventCandidate.score, 0)).label("avg_score"),
                func.avg(SearchEventCandidate.position).label("avg_position"),
            )
            .join(ServiceCatalog, ServiceCatalog.id == SearchEventCandidate.service_catalog_id)
            .join(ServiceSubcategory, ServiceSubcategory.id == ServiceCatalog.subcategory_id)
            .join(ServiceCategory, ServiceCategory.id == ServiceSubcategory.category_id)
            .filter(date_filter)
            .group_by(
                SearchEventCandidate.service_catalog_id,
                ServiceCatalog.name,
                ServiceCategory.name,
            )
            .order_by(func.count(SearchEventCandidate.id).desc())
            .limit(limit)
            .all()
        )

        return [
            TopServiceData(
                service_catalog_id=r.service_catalog_id,
                service_name=r.service_name,
                category_name=r.category_name,
                candidate_count=r.candidate_count,
                avg_score=float(r.avg_score or 0),
                avg_position=float(r.avg_position or 0),
            )
            for r in rows
        ]

    def get_service_instructor_counts(self, service_ids: List[str]) -> Dict[str, int]:
        """
        Get active instructor counts for services.

        Args:
            service_ids: List of service catalog IDs

        Returns:
            Dict mapping service_id to instructor count
        """
        if not service_ids:
            return {}

        rows = (
            self.db.query(
                InstructorService.service_catalog_id,
                func.count(InstructorService.id),
            )
            .filter(
                InstructorService.service_catalog_id.in_(service_ids),
                InstructorService.is_active == True,
            )
            .group_by(InstructorService.service_catalog_id)
            .all()
        )

        return {sid: cnt for sid, cnt in rows}

    def count_candidates_by_score_range(
        self,
        start_datetime: datetime,
        end_datetime: datetime,
        min_score: float,
        max_score: Optional[float] = None,
    ) -> int:
        """
        Count candidates within a score range.

        Args:
            start_datetime: Start of time range
            end_datetime: End of time range
            min_score: Minimum score (inclusive)
            max_score: Maximum score (exclusive), None for no upper bound

        Returns:
            Count of candidates in range
        """
        filters = [
            SearchEventCandidate.created_at >= start_datetime,
            SearchEventCandidate.created_at <= end_datetime,
        ]

        if max_score is not None:
            filters.append(SearchEventCandidate.score >= min_score)
            filters.append(SearchEventCandidate.score < max_score)
        else:
            filters.append(SearchEventCandidate.score >= min_score)

        return (
            self.db.query(func.count(SearchEventCandidate.id)).filter(and_(*filters)).scalar() or 0
        )

    def count_candidates_below_score(
        self, start_datetime: datetime, end_datetime: datetime, threshold: float
    ) -> int:
        """
        Count candidates below a score threshold.

        Args:
            start_datetime: Start of time range
            end_datetime: End of time range
            threshold: Score threshold

        Returns:
            Count of candidates below threshold
        """
        return (
            self.db.query(func.count(SearchEventCandidate.id))
            .filter(
                and_(
                    SearchEventCandidate.created_at >= start_datetime,
                    SearchEventCandidate.created_at <= end_datetime,
                    SearchEventCandidate.score < threshold,
                )
            )
            .scalar()
            or 0
        )

    def get_candidate_service_queries(
        self,
        service_catalog_id: str,
        start_datetime: datetime,
        end_datetime: datetime,
        limit: int = 50,
    ) -> List[CandidateServiceQueryData]:
        """
        Get queries that produced candidates for a service.

        Args:
            service_catalog_id: Service catalog ID
            start_datetime: Start of time range
            end_datetime: End of time range
            limit: Maximum results to return

        Returns:
            List of candidate service query data
        """
        rows = (
            self.db.query(
                SearchEvent.searched_at,
                SearchEvent.search_query,
                SearchEvent.results_count,
                SearchEventCandidate.position,
                SearchEventCandidate.score,
                SearchEventCandidate.source,
            )
            .join(SearchEvent, SearchEvent.id == SearchEventCandidate.search_event_id)
            .filter(
                SearchEventCandidate.service_catalog_id == service_catalog_id,
                SearchEventCandidate.created_at >= start_datetime,
                SearchEventCandidate.created_at <= end_datetime,
            )
            .order_by(SearchEvent.searched_at.desc(), SearchEventCandidate.position.asc())
            .limit(limit)
            .all()
        )

        return [
            CandidateServiceQueryData(
                searched_at=r.searched_at,
                search_query=r.search_query,
                results_count=r.results_count,
                position=r.position,
                score=float(r.score) if r.score is not None else None,
                source=r.source,
            )
            for r in rows
        ]
