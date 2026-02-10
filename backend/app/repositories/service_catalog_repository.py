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
import threading
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, TypedDict, TypeVar, cast

from sqlalchemy import distinct, or_, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query, Session, joinedload, selectinload
from sqlalchemy.sql import func

from ..models.instructor import InstructorProfile
from ..models.service_catalog import (
    InstructorService,
    ServiceAnalytics,
    ServiceCatalog,
    ServiceCategory,
)
from ..models.subcategory import ServiceSubcategory
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

TQuery = TypeVar("TQuery")

# Module-level pg_trgm detection cache (avoids per-request DB query)
_pg_trgm_available: Optional[bool] = None
_pg_trgm_lock = threading.Lock()


def _check_pg_trgm(db: Session) -> bool:
    """Check pg_trgm availability, cached across all repository instances."""
    global _pg_trgm_available
    if _pg_trgm_available is not None:
        return _pg_trgm_available
    with _pg_trgm_lock:
        if _pg_trgm_available is not None:
            return _pg_trgm_available
        try:
            result = db.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            ).first()
            _pg_trgm_available = result is not None
        except Exception as e:
            logger.warning("pg_trgm_detection_failed", extra={"error": str(e)})
            _pg_trgm_available = False
        return _pg_trgm_available


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


def _escape_like(value: str) -> str:
    """Escape SQL LIKE/ILIKE metacharacters (%, _, \\)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PopularServiceMetrics(TypedDict):
    service: ServiceCatalog
    analytics: ServiceAnalytics
    popularity_score: float


class MinimalServiceInfo(TypedDict):
    id: str
    name: str
    slug: str


class ServiceCatalogRepository(BaseRepository[ServiceCatalog]):
    """Repository for service catalog with vector search capabilities."""

    def __init__(self, db: Session):
        """Initialize with ServiceCatalog model."""
        super().__init__(db, ServiceCatalog)
        self._pg_trgm_available = _check_pg_trgm(db)

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

        except OperationalError:
            logger.error("db_connection_error_in_vector_search", exc_info=True)
            raise
        except Exception as e:
            logger.warning(
                "vector_search_degraded",
                extra={"error": str(e)},
                exc_info=True,
            )
            return []

    def search_services(
        self,
        query_text: Optional[str] = None,
        category_id: Optional[str] = None,
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
            search_pattern = f"%{_escape_like(query_text)}%"
            if self._pg_trgm_available:
                # Use trigram similarity when available
                query = query.filter(
                    or_(
                        text(
                            "(service_catalog.name % :q) OR (similarity(service_catalog.name, :q) >= 0.3)"
                        ).params(q=query_text),
                        text(
                            "(service_catalog.description IS NOT NULL AND ((service_catalog.description % :q) OR (similarity(service_catalog.description, :q) >= 0.3)))"
                        ).params(q=query_text),
                        text(
                            "EXISTS (SELECT 1 FROM unnest(service_catalog.search_terms) AS term WHERE lower(term) LIKE lower(:pattern))"
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
            query = query.join(
                ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id
            ).filter(ServiceSubcategory.category_id == category_id)

        if online_capable is not None:
            query = query.filter(ServiceCatalog.online_capable == online_capable)

        if requires_certification is not None:
            query = query.filter(ServiceCatalog.requires_certification == requires_certification)

        # Order by a hybrid of similarity then display_order/name when a query is present
        if query_text:
            if self._pg_trgm_available:
                query = query.order_by(
                    text("COALESCE(similarity(service_catalog.name, :q), 0) DESC").params(
                        q=query_text
                    ),
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

        Uses native PostgreSQL bulk UPDATE for maximum performance.

        Returns:
            Number of services updated
        """
        from psycopg2.extras import execute_values

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
        results = query.order_by(
            (ServiceAnalytics.booking_count_30d * 2 + ServiceAnalytics.search_count_30d).desc()
        ).all()

        if not results:
            return 0

        # Build values for bulk update: (id, display_order)
        values = [(service_id, idx + 1) for idx, (service_id, _, _) in enumerate(results)]

        # Native PostgreSQL UPDATE using VALUES pattern (1 round trip)
        connection = self.db.connection().connection
        update_sql = """
            UPDATE service_catalog AS t
            SET display_order = v.display_order,
                updated_at = NOW()
            FROM (VALUES %s) AS v(id, display_order)
            WHERE t.id = v.id
        """

        with connection.cursor() as cursor:
            execute_values(cursor, update_sql, values, template="(%s, %s::integer)", page_size=1000)

        # Expire all ORM objects to prevent stale reads after raw SQL update
        self.db.expire_all()

        return len(values)

    def _apply_eager_loading(self, query: Any) -> Any:
        """Apply eager loading for subcategory→category relationship."""
        return query.options(
            joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category)
        )

    def get_active_services_with_categories(
        self, category_id: Optional[str] = None, skip: int = 0, limit: Optional[int] = None
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
            .options(joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category))
            .filter(ServiceCatalog.is_active == True)
        )
        query = _apply_active_catalog_predicate(query)

        if category_id:
            query = query.join(
                ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id
            ).filter(ServiceSubcategory.category_id == category_id)

        # Order by display_order in database (not Python)
        query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)

        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        return cast(List[ServiceCatalog], query.all())

    def list_services_with_categories(
        self,
        *,
        include_inactive: bool = False,
    ) -> List[ServiceCatalog]:
        """
        List catalog services with subcategory→category eagerly loaded.

        Args:
            include_inactive: Whether to include inactive/deleted services

        Returns:
            List of ServiceCatalog objects with subcategory+category loaded
        """
        query = self.db.query(ServiceCatalog).options(
            joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category)
        )
        if not include_inactive:
            query = _apply_active_catalog_predicate(query)
        query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)
        return cast(List[ServiceCatalog], query.all())

    def search_services_with_categories(
        self,
        query_text: str,
        *,
        include_inactive: bool = False,
        limit: int = 25,
    ) -> List[ServiceCatalog]:
        """
        Search services with subcategory→category eagerly loaded.

        Args:
            query_text: Text to search in name, slug, description, and search_terms
            include_inactive: Whether to include inactive/deleted services
            limit: Maximum results

        Returns:
            List of matching services
        """
        query = self.db.query(ServiceCatalog).options(
            joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category)
        )
        if not include_inactive:
            query = _apply_active_catalog_predicate(query)

        search_pattern = f"%{query_text}%"
        if self._pg_trgm_available:
            query = query.filter(
                or_(
                    text(
                        "(service_catalog.name % :q) OR (similarity(service_catalog.name, :q) >= 0.3)"
                    ).params(q=query_text),
                    text(
                        "(service_catalog.slug % :q) OR (similarity(service_catalog.slug, :q) >= 0.3)"
                    ).params(q=query_text),
                    text(
                        "(service_catalog.description IS NOT NULL AND ((service_catalog.description % :q) OR (similarity(service_catalog.description, :q) >= 0.3)))"
                    ).params(q=query_text),
                    text(
                        "EXISTS (SELECT 1 FROM unnest(service_catalog.search_terms) AS term WHERE lower(term) LIKE lower(:pattern))"
                    ).params(pattern=search_pattern),
                )
            )
            query = query.order_by(
                text(
                    "GREATEST(similarity(service_catalog.name, :q), similarity(service_catalog.slug, :q)) DESC"
                ).params(q=query_text),
                ServiceCatalog.display_order,
                ServiceCatalog.name,
            )
        else:
            query = query.filter(
                or_(
                    ServiceCatalog.name.ilike(search_pattern),
                    ServiceCatalog.slug.ilike(search_pattern),
                    ServiceCatalog.description.ilike(search_pattern),
                    text(
                        "EXISTS (SELECT 1 FROM unnest(search_terms) AS term WHERE lower(term) LIKE lower(:pattern))"
                    ).params(pattern=search_pattern),
                )
            )
            query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)

        return cast(List[ServiceCatalog], query.limit(limit).all())

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

    def count_active_instructors_bulk(self, service_catalog_ids: List[str]) -> Dict[str, int]:
        """
        Count active instructors for multiple services in a single query.

        Args:
            service_catalog_ids: List of service catalog IDs

        Returns:
            Dict mapping service_catalog_id -> instructor count
        """
        from sqlalchemy import func

        if not service_catalog_ids:
            return {}

        query = self.db.query(
            InstructorService.service_catalog_id,
            func.count(InstructorService.id).label("count"),
        ).filter(InstructorService.service_catalog_id.in_(service_catalog_ids))
        query = _apply_instructor_service_active_filter(query)
        query = query.group_by(InstructorService.service_catalog_id)

        results = query.all()
        return {str(row.service_catalog_id): row.count for row in results}

    def get_services_needing_embedding(
        self, current_model: str, limit: int = 100
    ) -> List[ServiceCatalog]:
        """
        Find services that need embedding generation or update.

        Queries for:
        - Services with NULL embedding_v2
        - Services with different embedding_model than current
        - Services with stale embeddings (>30 days old)

        Args:
            current_model: The current embedding model name
            limit: Maximum number of services to return

        Returns:
            List of ServiceCatalog objects needing embedding
        """
        stale_threshold = datetime.now(timezone.utc) - timedelta(days=30)

        query = (
            self.db.query(ServiceCatalog)
            .filter(ServiceCatalog.is_active == True)  # noqa: E712
            .filter(
                or_(
                    ServiceCatalog.embedding_v2 == None,  # noqa: E711
                    ServiceCatalog.embedding_model != current_model,
                    ServiceCatalog.embedding_updated_at < stale_threshold,
                )
            )
            .limit(limit)
        )

        return cast(List[ServiceCatalog], query.all())

    def count_active_services(self) -> int:
        """Count all active services."""
        count = (
            self.db.query(ServiceCatalog)
            .filter(ServiceCatalog.is_active == True)  # noqa: E712
            .count()
        )
        return count or 0

    def count_services_missing_embedding(self) -> int:
        """Count active services that don't have embedding_v2."""
        count = (
            self.db.query(ServiceCatalog)
            .filter(
                ServiceCatalog.is_active == True,  # noqa: E712
                ServiceCatalog.embedding_v2 == None,  # noqa: E711
            )
            .count()
        )
        return count or 0

    def get_all_services_missing_embedding(self) -> List[ServiceCatalog]:
        """Get all active services without embeddings (no limit)."""
        query = self.db.query(ServiceCatalog).filter(
            ServiceCatalog.is_active == True,  # noqa: E712
            ServiceCatalog.embedding_v2 == None,  # noqa: E711
        )
        return cast(List[ServiceCatalog], query.all())

    def update_service_embedding(
        self,
        service_id: str,
        embedding: List[float],
        model_name: str,
        text_hash: str,
    ) -> bool:
        """
        Update a service's embedding in the database.

        Args:
            service_id: The service ID
            embedding: The embedding vector
            model_name: The model used for embedding
            text_hash: Hash of the text used for embedding

        Returns:
            True if update was successful
        """
        try:
            service = self.db.query(ServiceCatalog).filter(ServiceCatalog.id == service_id).first()

            if not service:
                return False

            service.embedding_v2 = embedding
            service.embedding_model = model_name
            service.embedding_model_version = model_name
            service.embedding_updated_at = datetime.now(timezone.utc)
            service.embedding_text_hash = text_hash

            self.db.flush()
            return True

        except Exception as e:
            logger.error(f"Failed to update embedding for {service_id}: {e}")
            self.db.rollback()
            return False

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
        except OperationalError:
            logger.error("db_connection_error_in_kids_services", exc_info=True)
            raise
        except Exception as e:
            logger.warning(
                "kids_available_services_degraded",
                extra={"error": str(e)},
                exc_info=True,
            )
            return []

    # ── Taxonomy-aware queries (3-level: category → subcategory → service) ──

    def get_categories_with_subcategories(self) -> List[ServiceCategory]:
        """Fetch all categories with subcategories eager-loaded.

        Returns:
            Categories ordered by display_order, each with subcategories loaded.
        """
        return cast(
            List[ServiceCategory],
            self.db.query(ServiceCategory)
            .options(
                selectinload(ServiceCategory.subcategories).selectinload(
                    ServiceSubcategory.services
                )
            )
            .order_by(ServiceCategory.display_order)
            .all(),
        )

    def get_category_tree(self, category_id: str) -> Optional[ServiceCategory]:
        """Full 3-level tree: category → subcategories → services.

        Args:
            category_id: ULID of the category

        Returns:
            Category with subcategories and services loaded, or None
        """
        return cast(
            Optional[ServiceCategory],
            self.db.query(ServiceCategory)
            .options(
                selectinload(ServiceCategory.subcategories).selectinload(
                    ServiceSubcategory.services
                )
            )
            .filter(ServiceCategory.id == category_id)
            .first(),
        )

    def get_subcategory_with_services(self, subcategory_id: str) -> Optional[ServiceSubcategory]:
        """Single subcategory with its services eager-loaded.

        Args:
            subcategory_id: ULID of the subcategory

        Returns:
            Subcategory with services loaded, or None
        """
        return cast(
            Optional[ServiceSubcategory],
            self.db.query(ServiceSubcategory)
            .options(selectinload(ServiceSubcategory.services))
            .filter(ServiceSubcategory.id == subcategory_id)
            .first(),
        )

    def get_subcategories_by_category(self, category_id: str) -> List[ServiceSubcategory]:
        """All subcategories for a category, ordered by display_order.

        Args:
            category_id: ULID of the parent category

        Returns:
            Ordered list of subcategories
        """
        return cast(
            List[ServiceSubcategory],
            self.db.query(ServiceSubcategory)
            .filter(ServiceSubcategory.category_id == category_id)
            .order_by(ServiceSubcategory.display_order)
            .all(),
        )

    def get_service_with_subcategory(self, service_id: str) -> Optional[ServiceCatalog]:
        """Single service with subcategory+category eager-loaded.

        Args:
            service_id: ULID of the service

        Returns:
            Service with subcategory→category chain loaded, or None
        """
        return cast(
            Optional[ServiceCatalog],
            self.db.query(ServiceCatalog)
            .options(joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category))
            .filter(ServiceCatalog.id == service_id)
            .first(),
        )

    def get_subcategory_ids_for_catalog_ids(self, service_catalog_ids: List[str]) -> Dict[str, str]:
        """Fetch subcategory IDs for a batch of service catalog IDs.

        Args:
            service_catalog_ids: Catalog IDs to resolve.

        Returns:
            Dict mapping service_catalog_id -> subcategory_id.
        """
        unique_catalog_ids = [
            service_id for service_id in dict.fromkeys(service_catalog_ids) if service_id
        ]
        if not unique_catalog_ids:
            return {}

        rows = (
            self.db.query(ServiceCatalog.id, ServiceCatalog.subcategory_id)
            .filter(ServiceCatalog.id.in_(unique_catalog_ids))
            .all()
        )
        return {
            str(catalog_id): str(subcategory_id)
            for catalog_id, subcategory_id in rows
            if catalog_id and subcategory_id
        }

    def search_services_by_name(self, query: str, limit: int = 15) -> List[ServiceCatalog]:
        """Text search across service names for autocomplete.

        Uses pg_trgm similarity if available, else ILIKE.

        Args:
            query: Search text
            limit: Max results

        Returns:
            Matching services ordered by relevance
        """
        base = self.db.query(ServiceCatalog).filter(ServiceCatalog.is_active.is_(True))
        base = _apply_active_catalog_predicate(base)

        if self._pg_trgm_available:
            base = base.filter(
                or_(
                    text(
                        "(service_catalog.name % :q) OR (similarity(service_catalog.name, :q) >= 0.3)"
                    ).params(q=query),
                    ServiceCatalog.name.ilike(f"%{query}%"),
                )
            ).order_by(
                text("similarity(service_catalog.name, :q) DESC").params(q=query),
                ServiceCatalog.display_order,
            )
        else:
            base = base.filter(ServiceCatalog.name.ilike(f"%{query}%")).order_by(
                ServiceCatalog.display_order, ServiceCatalog.name
            )

        return cast(List[ServiceCatalog], base.limit(limit).all())

    def get_by_slug(self, slug: str) -> Optional[ServiceCatalog]:
        """Look up a service by its URL slug.

        Args:
            slug: URL-friendly identifier (e.g., "piano-lessons").

        Returns:
            Service with subcategory→category chain loaded, or None.
        """
        return cast(
            Optional[ServiceCatalog],
            self.db.query(ServiceCatalog)
            .options(joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category))
            .filter(ServiceCatalog.slug == slug, ServiceCatalog.is_active.is_(True))
            .first(),
        )

    def get_by_subcategory(
        self, subcategory_id: str, active_only: bool = True
    ) -> List[ServiceCatalog]:
        """All services for a subcategory, ordered by display_order.

        Args:
            subcategory_id: ULID of the parent subcategory.
            active_only: Only return active services.

        Returns:
            Ordered list of services.
        """
        query = (
            self.db.query(ServiceCatalog)
            .filter(ServiceCatalog.subcategory_id == subcategory_id)
            .order_by(ServiceCatalog.display_order, ServiceCatalog.name)
        )

        if active_only:
            query = _apply_active_catalog_predicate(query)

        return cast(List[ServiceCatalog], query.all())

    def get_services_by_eligible_age_group(
        self, age_group: str, limit: int = 50
    ) -> List[ServiceCatalog]:
        """Services where eligible_age_groups array contains the given value.

        Args:
            age_group: e.g., "kids", "teens", "adults", "toddler"
            limit: Max results

        Returns:
            Active services matching the age group
        """
        query = self.db.query(ServiceCatalog).filter(ServiceCatalog.is_active.is_(True))
        query = _apply_active_catalog_predicate(query)

        # PostgreSQL array containment: ANY() on the array column
        query = query.filter(
            func.array_position(ServiceCatalog.eligible_age_groups, age_group).isnot(None)
        )

        return cast(
            List[ServiceCatalog],
            query.order_by(ServiceCatalog.display_order, ServiceCatalog.name).limit(limit).all(),
        )


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

        self.db.flush()
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
        existing = select(ServiceAnalytics.service_catalog_id).subquery()
        existing_ids = select(existing.c.service_catalog_id)

        # Find active services without analytics
        missing_rows = cast(
            Sequence[Tuple[str]],
            (
                _apply_active_catalog_predicate(
                    self.db.query(ServiceCatalog.id).filter(
                        ServiceCatalog.is_active == True, ~ServiceCatalog.id.in_(existing_ids)
                    )
                ).all()
            ),
        )

        return [row[0] for row in missing_rows]

    def get_all(self, skip: int = 0, limit: int = 10000) -> List[ServiceAnalytics]:
        """
        Get all analytics records.

        Args:
            skip: Number of records to skip (default 0)
            limit: Maximum number of records to return (default 10000)

        Returns:
            List of all ServiceAnalytics records
        """
        return cast(
            List[ServiceAnalytics],
            self.db.query(ServiceAnalytics).offset(skip).limit(limit).all(),
        )

    def get_or_create_bulk(self, service_catalog_ids: List[str]) -> Dict[str, ServiceAnalytics]:
        """
        Get or create analytics records for multiple services in bulk.

        Uses a single query to load existing, then batch-creates missing ones.

        Args:
            service_catalog_ids: List of service catalog IDs

        Returns:
            Dict mapping service_catalog_id -> ServiceAnalytics
        """
        if not service_catalog_ids:
            return {}

        # Load all existing in one query
        existing = cast(
            List[ServiceAnalytics],
            self.db.query(ServiceAnalytics)
            .filter(ServiceAnalytics.service_catalog_id.in_(service_catalog_ids))
            .all(),
        )

        result: Dict[str, ServiceAnalytics] = {a.service_catalog_id: a for a in existing}

        # Create missing ones
        now = datetime.now(timezone.utc)
        for service_id in service_catalog_ids:
            if service_id not in result:
                analytics = ServiceAnalytics(
                    service_catalog_id=service_id,
                    search_count_7d=0,
                    search_count_30d=0,
                    booking_count_7d=0,
                    booking_count_30d=0,
                    active_instructors=0,
                    last_calculated=now,
                )
                self.db.add(analytics)
                result[service_id] = analytics

        self.db.flush()
        return result

    def bulk_update_all(self, updates: List[Dict[str, Any]]) -> int:
        """
        Bulk update multiple analytics records using native PostgreSQL.

        Uses psycopg2's execute_values for maximum performance:
        - 1 round trip for 250 updates vs 250 round trips
        - ~250x faster for remote databases like Supabase

        Each dict in updates must have 'service_catalog_id' key plus update fields.

        Args:
            updates: List of dicts with service_catalog_id and fields to update

        Returns:
            Number of records updated
        """
        if not updates:
            return 0

        from psycopg2.extras import execute_values

        # Get raw psycopg2 connection
        connection = self.db.connection().connection

        # Build values list with all supported columns
        # Order: service_catalog_id, booking_count_7d, booking_count_30d, active_instructors,
        #        total_weekly_hours, avg_price_booked, price_p25, price_p50, price_p75,
        #        most_booked_duration, duration_distribution, completion_rate,
        #        peak_hours, peak_days, supply_demand_ratio, last_calculated
        values = []
        for u in updates:
            values.append(
                (
                    u.get("service_catalog_id"),
                    u.get("booking_count_7d", 0),
                    u.get("booking_count_30d", 0),
                    u.get("active_instructors", 0),
                    u.get("total_weekly_hours"),
                    u.get("avg_price_booked"),
                    u.get("price_percentile_25"),
                    u.get("price_percentile_50"),
                    u.get("price_percentile_75"),
                    u.get("most_booked_duration"),
                    u.get("duration_distribution"),
                    u.get("completion_rate"),
                    u.get("peak_hours"),
                    u.get("peak_days"),
                    u.get("supply_demand_ratio"),
                    u.get("last_calculated"),
                )
            )

        # Native PostgreSQL UPDATE using VALUES pattern (1 round trip)
        update_sql = """
            UPDATE service_analytics AS t
            SET booking_count_7d = v.booking_count_7d,
                booking_count_30d = v.booking_count_30d,
                active_instructors = v.active_instructors,
                total_weekly_hours = v.total_weekly_hours,
                avg_price_booked = v.avg_price_booked,
                price_percentile_25 = v.price_percentile_25,
                price_percentile_50 = v.price_percentile_50,
                price_percentile_75 = v.price_percentile_75,
                most_booked_duration = v.most_booked_duration,
                duration_distribution = v.duration_distribution,
                completion_rate = v.completion_rate,
                peak_hours = v.peak_hours,
                peak_days = v.peak_days,
                supply_demand_ratio = v.supply_demand_ratio,
                last_calculated = v.last_calculated
            FROM (VALUES %s) AS v(
                service_catalog_id, booking_count_7d, booking_count_30d,
                active_instructors, total_weekly_hours, avg_price_booked,
                price_percentile_25, price_percentile_50, price_percentile_75,
                most_booked_duration, duration_distribution, completion_rate,
                peak_hours, peak_days, supply_demand_ratio, last_calculated
            )
            WHERE t.service_catalog_id = v.service_catalog_id
        """

        template = """(
            %s, %s::integer, %s::integer, %s::integer, %s::float,
            %s::float, %s::float, %s::float, %s::float,
            %s::integer, %s::json, %s::float, %s::json, %s::json, %s::float,
            %s::timestamptz
        )"""

        with connection.cursor() as cursor:
            execute_values(cursor, update_sql, values, template=template, page_size=1000)

        # Expire all ORM objects to prevent stale reads after raw SQL update
        self.db.expire_all()

        return len(updates)
