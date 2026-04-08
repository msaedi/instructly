"""Write-side NL search analytics operations."""

from typing import Any, Dict, Optional

from ...models.service_catalog import InstructorService, ServiceCatalog
from .mixin_base import SearchAnalyticsRepositoryMixinBase


class NLSearchWriteMixin(SearchAnalyticsRepositoryMixinBase):
    """Raw-SQL write operations and click target resolution for NL search."""

    def nl_log_search_query(
        self,
        original_query: str,
        normalized_query: Dict[str, Any],
        parsing_mode: str,
        parsing_latency_ms: int,
        result_count: int,
        total_latency_ms: int,
        cache_hit: bool = False,
        degraded: bool = False,
        user_id: Optional[str] = None,
        query_id: Optional[str] = None,
    ) -> str:
        """
        Log a NL search query for analytics.

        Args:
            query_id: Optional pre-generated ID. If None, generates a new one.
                      Pass a pre-generated ID for fire-and-forget logging patterns.

        Returns the search_query_id for click tracking.
        """
        import json

        from sqlalchemy import text as sql_text

        from app.core.ulid_helper import generate_ulid

        if query_id is None:
            query_id = generate_ulid()

        query = sql_text(
            """
            INSERT INTO search_queries (
                id,
                original_query,
                normalized_query,
                parsing_mode,
                parsing_latency_ms,
                result_count,
                user_id,
                total_latency_ms,
                cache_hit,
                degraded,
                created_at
            ) VALUES (
                :id,
                :original_query,
                :normalized_query,
                :parsing_mode,
                :parsing_latency_ms,
                :result_count,
                :user_id,
                :total_latency_ms,
                :cache_hit,
                :degraded,
                NOW()
            )
        """
        )

        self.db.execute(
            query,
            {
                "id": query_id,
                "original_query": original_query,
                "normalized_query": json.dumps(normalized_query),
                "parsing_mode": parsing_mode,
                "parsing_latency_ms": parsing_latency_ms,
                "result_count": result_count,
                "user_id": user_id,
                "total_latency_ms": total_latency_ms,
                "cache_hit": cache_hit,
                "degraded": degraded,
            },
        )

        self.db.commit()
        return query_id

    def nl_resolve_click_targets(
        self,
        service_id: str,
        instructor_id: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve instructor-level click IDs to existing FK targets.

        The SearchClick table stores foreign keys to:
        - service_catalog.id
        - instructor_profiles.id

        The instructor-level search response and frontend click payloads use:
        - instructor_services.id (service_id)
        - users.id (instructor_id)

        Resolves those payload IDs to the stored foreign-key targets used by
        SearchClick. Values that are already in stored-ID form are accepted
        as-is. InstructorProfile is imported lazily inside this method to avoid
        a circular dependency at module load time.
        """
        from ...models.instructor import InstructorProfile

        # Resolve instructor_services.id -> service_catalog.id
        service_catalog_id: Optional[str] = (
            self.db.query(InstructorService.service_catalog_id)
            .filter(InstructorService.id == service_id)
            .scalar()
        )
        if not service_catalog_id:
            exists = (
                self.db.query(ServiceCatalog.id).filter(ServiceCatalog.id == service_id).first()
            )
            service_catalog_id = service_id if exists else None

        # Resolve users.id -> instructor_profiles.id
        instructor_profile_id: Optional[str] = (
            self.db.query(InstructorProfile.id)
            .filter(InstructorProfile.user_id == instructor_id)
            .scalar()
        )
        if not instructor_profile_id:
            exists = (
                self.db.query(InstructorProfile.id)
                .filter(InstructorProfile.id == instructor_id)
                .first()
            )
            instructor_profile_id = instructor_id if exists else None

        return service_catalog_id, instructor_profile_id

    def nl_log_search_click(
        self,
        search_query_id: str,
        service_id: str,
        instructor_id: str,
        position: int,
        action: str = "view",
    ) -> str:
        """
        Log a click/action on a NL search result.

        Actions: 'view', 'book', 'message', 'favorite'
        """
        from sqlalchemy import text as sql_text

        from app.core.ulid_helper import generate_ulid

        click_id: str = generate_ulid()

        query = sql_text(
            """
            INSERT INTO search_clicks (
                id,
                search_query_id,
                service_id,
                instructor_id,
                position,
                action,
                created_at
            ) VALUES (
                :id,
                :search_query_id,
                :service_id,
                :instructor_id,
                :position,
                :action,
                NOW()
            )
        """
        )

        self.db.execute(
            query,
            {
                "id": click_id,
                "search_query_id": search_query_id,
                "service_id": service_id,
                "instructor_id": instructor_id,
                "position": position,
                "action": action,
            },
        )

        self.db.commit()
        return click_id
