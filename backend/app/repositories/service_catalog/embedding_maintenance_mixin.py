"""Embedding maintenance queries and mutations for catalog services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, cast

from sqlalchemy import or_

from ...models.service_catalog import ServiceCatalog
from .mixin_base import ServiceCatalogRepositoryMixinBase


class EmbeddingMaintenanceMixin(ServiceCatalogRepositoryMixinBase):
    """Embedding maintenance queries and mutations for catalog services."""

    def get_services_needing_embedding(
        self, current_model: str, limit: int = 100
    ) -> List[ServiceCatalog]:
        """Find services that need embedding generation or update."""
        stale_threshold = datetime.now(timezone.utc) - timedelta(days=30)

        query = (
            self.db.query(ServiceCatalog)
            .filter(ServiceCatalog.is_active == True)
            .filter(
                or_(
                    ServiceCatalog.embedding_v2 == None,
                    ServiceCatalog.embedding_model != current_model,
                    ServiceCatalog.embedding_updated_at < stale_threshold,
                )
            )
            .limit(limit)
        )

        return cast(List[ServiceCatalog], query.all())

    def count_active_services(self) -> int:
        """Count all active services."""
        count = self.db.query(ServiceCatalog).filter(ServiceCatalog.is_active == True).count()
        return count or 0

    def count_services_missing_embedding(self) -> int:
        """Count active services that don't have embedding_v2."""
        count = (
            self.db.query(ServiceCatalog)
            .filter(
                ServiceCatalog.is_active == True,
                ServiceCatalog.embedding_v2 == None,
            )
            .count()
        )
        return count or 0

    def get_all_services_missing_embedding(self) -> List[ServiceCatalog]:
        """Get all active services without embeddings (no limit)."""
        query = self.db.query(ServiceCatalog).filter(
            ServiceCatalog.is_active == True,
            ServiceCatalog.embedding_v2 == None,
        )
        return cast(List[ServiceCatalog], query.all())

    def update_service_embedding(
        self,
        service_id: str,
        embedding: List[float],
        model_name: str,
        text_hash: str,
    ) -> bool:
        """Update a service's embedding in the database."""
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

        except Exception as exc:
            self.logger.error("Failed to update embedding for %s: %s", service_id, exc)
            self.db.rollback()
            return False
