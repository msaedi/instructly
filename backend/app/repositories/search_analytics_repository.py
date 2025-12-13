# backend/app/repositories/search_analytics_repository.py
"""
Search Analytics Repository for InstaInstru Platform.

Handles aggregate queries for search analytics dashboards.
Separates analytics-specific queries from basic CRUD operations.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import literal

from ..models.search_event import SearchEvent, SearchEventCandidate
from ..models.search_history import SearchHistory
from ..models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory


@dataclass
class DailySearchTrendData:
    """Daily search trend data."""

    date: date
    total_searches: int
    unique_users: int
    unique_guests: int


@dataclass
class PopularSearchData:
    """Popular search query data."""

    query: Optional[str]
    search_count: int
    unique_users: int
    average_results: float


@dataclass
class SearchReferrerData:
    """Search referrer data."""

    referrer: Optional[str]
    search_count: int
    unique_sessions: int


@dataclass
class SearchTotalsData:
    """Search totals aggregation."""

    total_searches: int
    unique_users: int
    unique_guests: int
    avg_results: float


@dataclass
class SearchTypeBreakdown:
    """Search type count."""

    search_type: Optional[str]
    count: int


@dataclass
class SearchEffectivenessData:
    """Search effectiveness metrics."""

    avg_results: float
    total_searches: int


@dataclass
class ProblematicQueryData:
    """Problematic search query data."""

    query: str
    count: int
    avg_results: float


@dataclass
class CandidateSummaryData:
    """Candidate summary data."""

    total_candidates: int
    events_with_candidates: int
    zero_result_events_with_candidates: int
    source_breakdown: Dict[str, int]


@dataclass
class CategoryTrendData:
    """Category trend data point."""

    date: date
    category: str
    count: int


@dataclass
class TopServiceData:
    """Top service candidate data."""

    service_catalog_id: str
    service_name: str
    category_name: str
    candidate_count: int
    avg_score: float
    avg_position: float


@dataclass
class ServiceSupplyData:
    """Active instructor count per service."""

    service_catalog_id: str
    count: int


@dataclass
class CandidateServiceQueryData:
    """Candidate service query data."""

    searched_at: Optional[datetime]
    search_query: Optional[str]
    results_count: Optional[int]
    position: Optional[int]
    score: Optional[float]
    source: Optional[str]


class SearchAnalyticsRepository:
    """Repository for search analytics aggregate queries."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_search_trends(self, start_date: date, end_date: date) -> List[DailySearchTrendData]:
        """
        Get daily search trends within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of daily search trend data
        """
        rows = (
            self.db.query(
                func.date(SearchEvent.searched_at).label("date"),
                func.count(SearchEvent.id).label("total_searches"),
                func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
                func.count(func.distinct(SearchEvent.guest_session_id)).label("unique_guests"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                )
            )
            .group_by(func.date(SearchEvent.searched_at))
            .order_by(func.date(SearchEvent.searched_at))
            .all()
        )

        return [
            DailySearchTrendData(
                date=row.date,
                total_searches=row.total_searches,
                unique_users=row.unique_users or 0,
                unique_guests=row.unique_guests or 0,
            )
            for row in rows
        ]

    def get_popular_searches(
        self, start_date: date, end_date: date, limit: int = 20
    ) -> List[PopularSearchData]:
        """
        Get most popular search queries within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum results to return

        Returns:
            List of popular search data
        """
        rows = (
            self.db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("search_count"),
                func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
                func.avg(SearchEvent.results_count).label("average_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.search_query.isnot(None),
                    SearchEvent.search_query != "",
                )
            )
            .group_by(SearchEvent.search_query)
            .order_by(desc("search_count"))
            .limit(limit)
            .all()
        )

        return [
            PopularSearchData(
                query=row.search_query,
                search_count=row.search_count,
                unique_users=row.unique_users or 0,
                average_results=round(row.average_results or 0, 2),
            )
            for row in rows
        ]

    def get_search_referrers(self, start_date: date, end_date: date) -> List[SearchReferrerData]:
        """
        Get pages that drive searches (referrers).

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of referrer data
        """
        rows = (
            self.db.query(
                SearchEvent.referrer,
                func.count(SearchEvent.id).label("search_count"),
                func.count(func.distinct(SearchEvent.session_id)).label("unique_sessions"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.referrer.isnot(None),
                    SearchEvent.referrer != "",
                )
            )
            .group_by(SearchEvent.referrer)
            .order_by(desc("search_count"))
            .all()
        )

        return [
            SearchReferrerData(
                referrer=row.referrer,
                search_count=row.search_count,
                unique_sessions=row.unique_sessions or 0,
            )
            for row in rows
        ]

    def get_search_totals(self, start_date: date, end_date: date) -> SearchTotalsData:
        """
        Get aggregate search totals within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Search totals data
        """
        row = (
            self.db.query(
                func.count(SearchEvent.id).label("total_searches"),
                func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
                func.count(func.distinct(SearchEvent.guest_session_id)).label("unique_guests"),
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                )
            )
            .first()
        )

        return SearchTotalsData(
            total_searches=row.total_searches or 0,
            unique_users=row.unique_users or 0,
            unique_guests=row.unique_guests or 0,
            avg_results=float(row.avg_results or 0),
        )

    def get_search_type_breakdown(
        self, start_date: date, end_date: date
    ) -> List[SearchTypeBreakdown]:
        """
        Get search type distribution within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of search type counts
        """
        rows = (
            self.db.query(SearchEvent.search_type, func.count(SearchEvent.id).label("count"))
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                )
            )
            .group_by(SearchEvent.search_type)
            .all()
        )

        return [SearchTypeBreakdown(search_type=row.search_type, count=row.count) for row in rows]

    def count_deleted_searches(self, start_date: date, end_date: date) -> int:
        """
        Count deleted searches within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of deleted searches
        """
        return (
            self.db.query(func.count(SearchHistory.id))
            .filter(
                and_(
                    SearchHistory.deleted_at.isnot(None),
                    func.date(SearchHistory.deleted_at) >= start_date,
                    func.date(SearchHistory.deleted_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def count_guest_sessions(self, start_date: date, end_date: date) -> int:
        """
        Count unique guest sessions within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of unique guest sessions
        """
        return (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def count_converted_guests(self, start_date: date, end_date: date) -> int:
        """
        Count guest sessions that converted to users.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of converted guest sessions
        """
        return (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.isnot(None),
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def count_zero_result_searches(self, start_date: date, end_date: date) -> int:
        """
        Count searches with zero results.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of zero result searches
        """
        return (
            self.db.query(func.count(SearchEvent.id))
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count == 0,
                )
            )
            .scalar()
            or 0
        )

    def get_most_effective_search_type(
        self, start_date: date, end_date: date
    ) -> Optional[Tuple[str, float]]:
        """
        Get search type with highest average results.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Tuple of (search_type, avg_results) or None
        """
        row = (
            self.db.query(
                SearchEvent.search_type,
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                )
            )
            .group_by(SearchEvent.search_type)
            .order_by(desc("avg_results"))
            .first()
        )

        if row:
            return (row.search_type, float(row.avg_results or 0))
        return None

    def count_engaged_guest_sessions(self, start_date: date, end_date: date) -> int:
        """
        Count guest sessions with multiple searches.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of engaged guest sessions
        """
        return (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.search_count > 1,
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def get_avg_searches_per_guest(self, start_date: date, end_date: date) -> float:
        """
        Get average searches per guest session.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Average searches per guest session
        """
        return (
            self.db.query(func.avg(SearchHistory.search_count))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def count_searches_in_result_range(
        self, start_date: date, end_date: date, min_results: int, max_results: Optional[int] = None
    ) -> int:
        """
        Count searches with results in a specific range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            min_results: Minimum result count (inclusive)
            max_results: Maximum result count (inclusive), None for no upper bound

        Returns:
            Count of searches in range
        """
        filters = [
            func.date(SearchEvent.searched_at) >= start_date,
            func.date(SearchEvent.searched_at) <= end_date,
            SearchEvent.results_count.isnot(None),
        ]

        if max_results is not None:
            filters.append(SearchEvent.results_count.between(min_results, max_results))
        else:
            filters.append(SearchEvent.results_count >= min_results)

        return self.db.query(func.count(SearchEvent.id)).filter(and_(*filters)).scalar() or 0

    def get_search_effectiveness(self, start_date: date, end_date: date) -> SearchEffectivenessData:
        """
        Get search effectiveness metrics.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Search effectiveness data
        """
        row = (
            self.db.query(
                func.avg(SearchEvent.results_count).label("avg_results"),
                func.count(SearchEvent.id).label("total_searches"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                )
            )
            .first()
        )

        return SearchEffectivenessData(
            avg_results=float(row.avg_results or 0),
            total_searches=row.total_searches or 0,
        )

    def count_searches_with_results(self, start_date: date, end_date: date) -> int:
        """
        Count searches that returned at least one result.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of searches with results
        """
        return (
            self.db.query(func.count(SearchEvent.id))
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                    SearchEvent.results_count > 0,
                )
            )
            .scalar()
            or 0
        )

    def get_problematic_queries(
        self, start_date: date, end_date: date, min_count: int = 5, limit: int = 10
    ) -> List[ProblematicQueryData]:
        """
        Get queries with low average results.

        Args:
            start_date: Start of date range
            end_date: End of date range
            min_count: Minimum search count to consider
            limit: Maximum results to return

        Returns:
            List of problematic query data
        """
        rows = (
            self.db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("count"),
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                    SearchEvent.search_query.isnot(None),
                    SearchEvent.search_query != "",
                )
            )
            .group_by(SearchEvent.search_query)
            .having(func.count(SearchEvent.id) >= min_count)
            .order_by(func.avg(SearchEvent.results_count))
            .limit(limit)
            .all()
        )

        return [
            ProblematicQueryData(
                query=row.search_query,
                count=row.count,
                avg_results=round(row.avg_results or 0, 2),
            )
            for row in rows
        ]

    # ===== Candidate Analytics Methods =====

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
                .outerjoin(ServiceCategory, ServiceCategory.id == ServiceCatalog.category_id)
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
            .join(ServiceCategory, ServiceCategory.id == ServiceCatalog.category_id)
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
