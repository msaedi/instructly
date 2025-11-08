# backend/app/repositories/service_catalog_repository.py
"""
Service Catalog Repository for Natural Language Search and Analytics

Provides specialized queries for:
- Vector similarity search using pgvector
- Analytics data retrieval and updates
- Filtering services by various criteria
- Optimized queries for service discovery

This repository extends BaseRepository with search and analytics capabilities.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, TypedDict, TypeVar, cast

from sqlalchemy import distinct, or_, text
from sqlalchemy.orm import Query, Session, joinedload
from sqlalchemy.sql import func

from ..models.instructor import InstructorProfile
from ..models.service_catalog import InstructorService, ServiceAnalytics, ServiceCatalog
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

TQuery = TypeVar("TQuery")


def _apply_active_catalog_predicate(query: Query[TQuery]) -> Query[TQuery]:
    """Ensure catalog queries exclude soft-deleted or inactive entries."""
    if hasattr(ServiceCatalog, "is_active"):
        query = cast(Query[TQuery], query.filter(ServiceCatalog.is_active.is_(True)))
    if hasattr(ServiceCatalog, "is_deleted"):
        query = cast(Query[TQuery], query.filter(ServiceCatalog.is_deleted.is_(False)))
    if hasattr(ServiceCatalog, "deleted_at"):
        query = cast(Query[TQuery], query.filter(ServiceCatalog.deleted_at.is_(None)))
    return query


def _apply_instructor_service_active_filter(query: Query[TQuery]) -> Query[TQuery]:
    """Ensure instructor service soft deletes are excluded."""
    if hasattr(InstructorService, "is_active"):
        query = cast(Query[TQuery], query.filter(InstructorService.is_active.is_(True)))
    if hasattr(InstructorService, "is_deleted"):
        query = cast(Query[TQuery], query.filter(InstructorService.is_deleted.is_(False)))
    if hasattr(InstructorService, "deleted_at"):
        query = cast(Query[TQuery], query.filter(InstructorService.deleted_at.is_(None)))
    return query


class PopularServiceMetrics(TypedDict):
    service: ServiceCatalog
    analytics: ServiceAnalytics
    popularity_score: float


class MinimalServiceInfo(TypedDict):
    id: int
    name: str
    slug: str


class ServiceCatalogRepository(BaseRepository[ServiceCatalog]):
    """Repository for service catalog with vector search capabilities."""

    def __init__(self, db: Session):
        """Initialize with ServiceCatalog model."""
        super().__init__(db, ServiceCatalog)
        # Detect pg_trgm availability once per repository instance
        self._pg_trgm_available = False
        try:
            res = self.db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
            self._pg_trgm_available = bool(res.fetchone())
        except Exception:
            self._pg_trgm_available = False

    def find_similar_by_embedding(
        self, embedding: List[float], limit: int = 10, threshold: float = 0.8
    ) -> List[Tuple[ServiceCatalog, float]]:
        """
        Find services similar to the given embedding using cosine similarity.

        Args:
            embedding: Query embedding vector (384 dimensions)
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0-1)

        Returns:
            List of tuples (service, similarity_score)
        """
        try:
            # Convert embedding to PostgreSQL array format
            embedding_str = f"[{','.join(map(str, embedding))}]"

            # Use raw SQL for vector similarity search
            sql = text(
                """
                SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) as similarity
                FROM service_catalog
                WHERE is_active = true
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """
            )

            result = self.db.execute(
                sql, {"embedding": embedding_str, "threshold": threshold, "limit": limit}
            )

            # Fetch services by IDs
            rows = result.fetchall()
            if not rows:
                return []

            # Get services
            service_ids = [row.id for row in rows]
            services_query = self.db.query(ServiceCatalog).filter(
                ServiceCatalog.id.in_(service_ids)
            )
            services = _apply_active_catalog_predicate(services_query).all()

            # Create service lookup
            service_map = {s.id: s for s in services}

            # Return services with scores in order
            return [(service_map[row.id], row.similarity) for row in rows if row.id in service_map]

        except Exception as e:
            logger.error(f"Error in vector similarity search: {str(e)}")
            return []

    def search_services(
        self,
        query_text: Optional[str] = None,
        category_id: Optional[int] = None,
        online_capable: Optional[bool] = None,
        requires_certification: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ServiceCatalog]:
        """
        Search services with text and filters.

        Args:
            query_text: Text to search in name, description, and search_terms
            category_id: Filter by category
            online_capable: Filter by online capability
            requires_certification: Filter by certification requirement
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching services
        """
        query = self.db.query(ServiceCatalog)
        query = _apply_active_catalog_predicate(query)

        # Text search across multiple fields
        if query_text:
            search_pattern = f"%{query_text}%"
            if self._pg_trgm_available:
                # Use trigram similarity when available
                query = query.filter(
                    or_(
                        text("(name % :q) OR (similarity(name, :q) >= 0.3)").params(q=query_text),
                        text(
                            "(description IS NOT NULL AND ((description % :q) OR (similarity(description, :q) >= 0.3)))"
                        ).params(q=query_text),
                        text(
                            "EXISTS (SELECT 1 FROM unnest(search_terms) AS term WHERE lower(term) LIKE lower(:pattern))"
                        ).params(pattern=search_pattern),
                    )
                )
            else:
                # Fallback to ILIKE + search_terms
                query = query.filter(
                    or_(
                        ServiceCatalog.name.ilike(search_pattern),
                        ServiceCatalog.description.ilike(search_pattern),
                        text(
                            "EXISTS (SELECT 1 FROM unnest(search_terms) AS term WHERE lower(term) LIKE lower(:pattern))"
                        ).params(pattern=search_pattern),
                    )
                )

        # Apply filters
        if category_id is not None:
            query = query.filter(ServiceCatalog.category_id == category_id)

        if online_capable is not None:
            query = query.filter(ServiceCatalog.online_capable == online_capable)

        if requires_certification is not None:
            query = query.filter(ServiceCatalog.requires_certification == requires_certification)

        # Order by a hybrid of similarity then display_order/name when a query is present
        if query_text:
            if self._pg_trgm_available:
                query = query.order_by(
                    text("COALESCE(similarity(name, :q), 0) DESC").params(q=query_text),
                    ServiceCatalog.display_order,
                    ServiceCatalog.name,
                )
            else:
                query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)
        else:
            query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)

        # Apply pagination
        return cast(List[ServiceCatalog], query.offset(skip).limit(limit).all())

    def get_popular_services(self, limit: int = 10, days: int = 30) -> List[PopularServiceMetrics]:
        """
        Get most popular services based on analytics.

        Args:
            limit: Number of services to return
            days: Look back period for analytics

        Returns:
            List of services with popularity metrics
        """
        # Join with analytics table
        query = (
            self.db.query(ServiceCatalog, ServiceAnalytics)
            .join(ServiceAnalytics, ServiceCatalog.id == ServiceAnalytics.service_catalog_id)
            .filter(ServiceCatalog.is_active == True)
        )
        query = _apply_active_catalog_predicate(query)

        # Order by booking count
        if days == 7:
            query = query.order_by(ServiceAnalytics.booking_count_7d.desc())
        else:
            query = query.order_by(ServiceAnalytics.booking_count_30d.desc())

        results = cast(List[Tuple[ServiceCatalog, ServiceAnalytics]], query.limit(limit).all())

        return [
            cast(
                PopularServiceMetrics,
                {
                    "service": service,
                    "analytics": analytics,
                    "popularity_score": float(getattr(analytics, "demand_score", 0.0)),
                },
            )
            for service, analytics in results
        ]

    def get_trending_services(self, limit: int = 10) -> List[ServiceCatalog]:
        """
        Get services that are trending upward in demand.

        Args:
            limit: Number of services to return

        Returns:
            List of trending services
        """
        # Subquery to calculate trend
        trend_subquery = self.db.query(
            ServiceAnalytics.service_catalog_id,
            (ServiceAnalytics.search_count_7d / 7.0).label("avg_7d"),
            (ServiceAnalytics.search_count_30d / 30.0).label("avg_30d"),
        ).subquery()

        # Main query joining with trend calculation
        query = (
            self.db.query(ServiceCatalog)
            .join(trend_subquery, ServiceCatalog.id == trend_subquery.c.service_catalog_id)
            .filter(
                ServiceCatalog.is_active == True,
                trend_subquery.c.avg_7d > trend_subquery.c.avg_30d * 1.2,  # 20% growth
            )
            .order_by((trend_subquery.c.avg_7d - trend_subquery.c.avg_30d).desc())
        )
        query = _apply_active_catalog_predicate(query)

        return cast(List[ServiceCatalog], query.limit(limit).all())

    def update_display_order_by_popularity(self) -> int:
        """
        Update display_order based on popularity metrics.

        Returns:
            Number of services updated
        """
        # Get services with analytics ordered by demand
        query = (
            self.db.query(
                ServiceCatalog.id,
                ServiceAnalytics.booking_count_30d,
                ServiceAnalytics.search_count_30d,
            )
            .join(ServiceAnalytics, ServiceCatalog.id == ServiceAnalytics.service_catalog_id)
            .filter(ServiceCatalog.is_active == True)
        )
        query = _apply_active_catalog_predicate(query)
        query = query.order_by(
            (ServiceAnalytics.booking_count_30d * 2 + ServiceAnalytics.search_count_30d).desc()
        ).all()

        # Update display orders
        updates = []
        for idx, (service_id, _, _) in enumerate(query):
            updates.append({"id": service_id, "display_order": idx + 1})  # 1-based ordering

        # Bulk update
        if updates:
            return self.bulk_update(updates)

        return 0

    def _apply_eager_loading(self, query: Any) -> Any:
        """Apply eager loading for category relationship."""
        return query.options(joinedload(ServiceCatalog.category))

    def get_active_services_with_categories(
        self, category_id: Optional[int] = None, skip: int = 0, limit: Optional[int] = None
    ) -> List[ServiceCatalog]:
        """
        Get active services with categories eagerly loaded, ordered by display_order.

        Optimized for the catalog endpoint to prevent N+1 queries.

        Args:
            category_id: Optional category filter
            skip: Pagination offset
            limit: Maximum results (None for all)

        Returns:
            List of ServiceCatalog objects with categories loaded
        """
        query = (
            self.db.query(ServiceCatalog)
            .options(joinedload(ServiceCatalog.category))
            .filter(ServiceCatalog.is_active == True)
        )
        query = _apply_active_catalog_predicate(query)

        if category_id:
            query = query.filter(ServiceCatalog.category_id == category_id)

        # Order by display_order in database (not Python)
        query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)

        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        return cast(List[ServiceCatalog], query.all())

    def count_active_instructors(self, service_catalog_id: str) -> int:
        """
        Count the number of active instructors offering a specific service.

        Args:
            service_catalog_id: The service catalog ID to count instructors for

        Returns:
            Number of active instructors offering this service
        """
        from sqlalchemy import func

        query = self.db.query(func.count(InstructorService.id)).filter(
            InstructorService.service_catalog_id == service_catalog_id
        )
        query = _apply_instructor_service_active_filter(query)
        count = query.scalar()

        return count or 0

    def get_services_available_for_kids_minimal(self) -> List[MinimalServiceInfo]:
        """
        Return minimal info for catalog services that have at least one active instructor
        whose age_groups includes 'kids'.

        Returns:
            List of dicts: {"id", "name", "slug"}
        """
        try:
            # Join instructor services to catalog and filter by kids-capable
            query = (
                self.db.query(
                    distinct(ServiceCatalog.id).label("id"),
                    ServiceCatalog.name.label("name"),
                    ServiceCatalog.slug.label("slug"),
                )
                .join(InstructorService, InstructorService.service_catalog_id == ServiceCatalog.id)
                .join(
                    InstructorProfile,
                    InstructorService.instructor_profile_id == InstructorProfile.id,
                )
                .join(User, InstructorProfile.user_id == User.id)
                .filter(InstructorService.is_active == True)
                .filter(User.account_status == "active")
            )
            query = _apply_instructor_service_active_filter(query)
            query = _apply_active_catalog_predicate(query)

            # Postgres: use array_position for membership; fallback: LIKE for JSON/text storage
            if self.dialect_name == "postgresql":
                query = query.filter(
                    func.array_position(InstructorService.age_groups, "kids").isnot(None)
                )
            else:
                query = query.filter(InstructorService.age_groups.like('%"kids"%'))

            rows = cast(Sequence[Any], query.all())
            return [
                cast(MinimalServiceInfo, {"id": r.id, "name": r.name, "slug": r.slug}) for r in rows
            ]
        except Exception as e:
            logger.error(f"Error fetching kids-available services: {str(e)}")
            return []


class ServiceAnalyticsRepository(BaseRepository[ServiceAnalytics]):
    """Repository for service analytics data."""

    def __init__(self, db: Session):
        """Initialize with ServiceAnalytics model."""
        super().__init__(db, ServiceAnalytics)

    def get_by_id(self, id: Any, load_relationships: bool = True) -> Optional[ServiceAnalytics]:
        """
        Override get_by_id to use service_catalog_id as primary key.

        Args:
            id: The service catalog ID (primary key)
            load_relationships: Whether to load relationships

        Returns:
            ServiceAnalytics instance or None
        """
        service_catalog_id = cast(str, id)
        return self.find_one_by(service_catalog_id=service_catalog_id)

    def update(self, id: Any, **kwargs: Any) -> Optional[ServiceAnalytics]:
        """
        Override update to use service_catalog_id as primary key.

        Args:
            id: The service catalog ID (primary key)
            **kwargs: Fields to update

        Returns:
            Updated ServiceAnalytics instance
        """
        service_catalog_id = cast(str, id)
        entity = self.find_one_by(service_catalog_id=service_catalog_id)
        if not entity:
            return None

        for key, value in kwargs.items():
            setattr(entity, key, value)

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_or_create(self, service_catalog_id: str) -> ServiceAnalytics:
        """
        Get existing analytics or create new with defaults.

        Args:
            service_catalog_id: Service catalog ID

        Returns:
            ServiceAnalytics instance
        """
        analytics = self.find_one_by(service_catalog_id=service_catalog_id)

        if not analytics:
            analytics = self.create(
                service_catalog_id=service_catalog_id,
                search_count_7d=0,
                search_count_30d=0,
                booking_count_7d=0,
                booking_count_30d=0,
                active_instructors=0,
                last_calculated=datetime.now(timezone.utc),
            )

        return analytics

    def increment_search_count(self, service_catalog_id: str) -> None:
        """
        Increment search count for a service.

        Args:
            service_catalog_id: Service catalog ID
        """
        analytics = self.get_or_create(service_catalog_id)

        # Increment both 7d and 30d counters
        self.update(
            analytics.service_catalog_id,
            search_count_7d=analytics.search_count_7d + 1,
            search_count_30d=analytics.search_count_30d + 1,
        )

    def get_stale_analytics(self, hours: int = 24) -> List[ServiceAnalytics]:
        """
        Get analytics records that need updating.

        Args:
            hours: Consider stale if older than this many hours

        Returns:
            List of stale analytics records
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        return cast(
            List[ServiceAnalytics],
            self.db.query(ServiceAnalytics).filter(ServiceAnalytics.last_calculated < cutoff).all(),
        )

    def update_from_bookings(
        self, service_catalog_id: str, booking_stats: Mapping[str, Any]
    ) -> None:
        """
        Update analytics from booking statistics.

        Args:
            service_catalog_id: Service catalog ID
            booking_stats: Dictionary with booking metrics
        """
        analytics = self.get_or_create(service_catalog_id)

        updates: Dict[str, Any] = {
            "booking_count_7d": booking_stats.get("count_7d", 0),
            "booking_count_30d": booking_stats.get("count_30d", 0),
            "avg_price_booked": booking_stats.get("avg_price"),
            "price_percentile_25": booking_stats.get("price_p25"),
            "price_percentile_50": booking_stats.get("price_p50"),
            "price_percentile_75": booking_stats.get("price_p75"),
            "most_booked_duration": booking_stats.get("most_popular_duration"),
            "completion_rate": booking_stats.get("completion_rate"),
            "avg_rating": booking_stats.get("avg_rating"),
            "last_calculated": datetime.now(timezone.utc),
        }

        # Remove None values
        updates = {k: v for k, v in updates.items() if v is not None}

        self.update(analytics.service_catalog_id, **updates)

    def get_services_needing_analytics(self) -> List[str]:
        """
        Get service IDs that don't have analytics records.

        Returns:
            List of service catalog IDs
        """
        # Subquery for existing analytics
        existing = self.db.query(ServiceAnalytics.service_catalog_id).subquery()

        # Find active services without analytics
        missing_rows = cast(
            Sequence[Tuple[str]],
            (
                _apply_active_catalog_predicate(
                    self.db.query(ServiceCatalog.id).filter(
                        ServiceCatalog.is_active == True, ~ServiceCatalog.id.in_(existing)
                    )
                ).all()
            ),
        )

        return [row[0] for row in missing_rows]
