"""Search and discovery queries for catalog services."""

from __future__ import annotations

from typing import List, Optional, Tuple, cast

from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import func, text

from ...models.service_catalog import ServiceCatalog
from ...models.subcategory import ServiceSubcategory
from .mixin_base import ServiceCatalogRepositoryMixinBase


class CatalogSearchMixin(ServiceCatalogRepositoryMixinBase):
    """Search and discovery queries for catalog services."""

    def find_similar_by_embedding(
        self, embedding: List[float], limit: int = 10, threshold: float = 0.8
    ) -> List[Tuple[ServiceCatalog, float]]:
        """
        Find services similar to the given embedding using cosine similarity.

        Args:
            embedding: Query embedding vector (1536 dimensions)
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0-1)

        Returns:
            List of tuples (service, similarity_score)
        """
        try:
            embedding_str = f"[{','.join(map(str, embedding))}]"
            sql = text(
                """
                SELECT id, 1 - (embedding_v2 <=> CAST(:embedding AS vector)) as similarity
                FROM service_catalog
                WHERE is_active = true
                  AND embedding_v2 IS NOT NULL
                  AND 1 - (embedding_v2 <=> CAST(:embedding AS vector)) >= :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """
            )

            result = self.db.execute(
                sql, {"embedding": embedding_str, "threshold": threshold, "limit": limit}
            )
            rows = result.fetchall()
            if not rows:
                return []

            service_ids = [row.id for row in rows]
            services_query = self.db.query(ServiceCatalog).filter(
                ServiceCatalog.id.in_(service_ids)
            )
            services = self._apply_active_catalog_predicate(services_query).all()
            service_map = {service.id: service for service in services}

            return [(service_map[row.id], row.similarity) for row in rows if row.id in service_map]

        except OperationalError:
            self.logger.error("db_connection_error_in_vector_search", exc_info=True)
            raise
        except Exception as exc:
            self.logger.error(
                "vector_search_degraded",
                extra={"error": str(exc)},
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
        query = self._apply_active_catalog_predicate(query)

        if query_text:
            search_pattern = f"%{self._escape_like(query_text)}%"
            if self._pg_trgm_available:
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
                query = query.filter(
                    or_(
                        ServiceCatalog.name.ilike(search_pattern),
                        ServiceCatalog.description.ilike(search_pattern),
                        text(
                            "EXISTS (SELECT 1 FROM unnest(search_terms) AS term WHERE lower(term) LIKE lower(:pattern))"
                        ).params(pattern=search_pattern),
                    )
                )

        if category_id is not None:
            query = query.join(
                ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id
            ).filter(ServiceSubcategory.category_id == category_id)

        if online_capable is not None:
            query = query.filter(ServiceCatalog.online_capable == online_capable)

        if requires_certification is not None:
            query = query.filter(ServiceCatalog.requires_certification == requires_certification)

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

        return cast(List[ServiceCatalog], query.offset(skip).limit(limit).all())

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
        query = self._apply_eager_loading(self.db.query(ServiceCatalog))
        if not include_inactive:
            query = self._apply_active_catalog_predicate(query)

        search_pattern = f"%{self._escape_like(query_text)}%"
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

    def search_services_by_name(self, query: str, limit: int = 15) -> List[ServiceCatalog]:
        """Text search across service names for autocomplete."""
        base = self.db.query(ServiceCatalog).filter(ServiceCatalog.is_active.is_(True))
        base = self._apply_active_catalog_predicate(base)

        escaped_query = self._escape_like(query)
        if self._pg_trgm_available:
            base = base.filter(
                or_(
                    text(
                        "(service_catalog.name % :q) OR (similarity(service_catalog.name, :q) >= 0.3)"
                    ).params(q=query),
                    ServiceCatalog.name.ilike(f"%{escaped_query}%"),
                )
            ).order_by(
                text("similarity(service_catalog.name, :q) DESC").params(q=query),
                ServiceCatalog.display_order,
            )
        else:
            base = base.filter(ServiceCatalog.name.ilike(f"%{escaped_query}%")).order_by(
                ServiceCatalog.display_order, ServiceCatalog.name
            )

        return cast(List[ServiceCatalog], base.limit(limit).all())

    def get_services_by_eligible_age_group(
        self, age_group: str, limit: int = 50
    ) -> List[ServiceCatalog]:
        """Services where eligible_age_groups array contains the given value."""
        query = self.db.query(ServiceCatalog).filter(ServiceCatalog.is_active.is_(True))
        query = self._apply_active_catalog_predicate(query)
        query = query.filter(
            func.array_position(ServiceCatalog.eligible_age_groups, age_group).isnot(None)
        )

        return cast(
            List[ServiceCatalog],
            query.order_by(ServiceCatalog.display_order, ServiceCatalog.name).limit(limit).all(),
        )
