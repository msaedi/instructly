"""Shared typing surface for service catalog repository mixins."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Query, Session

from ...models.service_catalog import ServiceAnalytics, ServiceCatalog

if TYPE_CHECKING:

    class ServiceCatalogRepositoryMixinBase:
        """Typed attribute/method surface supplied by the service catalog facade."""

        db: Session
        logger: logging.Logger
        model: type[ServiceCatalog]
        dialect_name: str
        _pg_trgm_available: bool

        def _apply_eager_loading(self, query: Query[Any]) -> Query[Any]:
            ...

        @staticmethod
        def _apply_active_catalog_predicate(query: Query[Any]) -> Query[Any]:
            ...

        @staticmethod
        def _apply_instructor_service_active_filter(query: Query[Any]) -> Query[Any]:
            ...

        @staticmethod
        def _escape_like(value: str) -> str:
            ...

else:

    class ServiceCatalogRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
        model: type[ServiceCatalog]
        dialect_name: str
        _pg_trgm_available: bool


if TYPE_CHECKING:

    class ServiceAnalyticsRepositoryMixinBase:
        """Typed attribute/method surface supplied by the service analytics facade."""

        db: Session
        logger: logging.Logger
        model: type[ServiceAnalytics]

        def find_one_by(self, **kwargs: Any) -> Optional[ServiceAnalytics]:
            ...

        def create(self, **kwargs: Any) -> ServiceAnalytics:
            ...

        def update(self, id: Any, **kwargs: Any) -> Optional[ServiceAnalytics]:
            ...

        def get_or_create(self, service_catalog_id: str) -> ServiceAnalytics:
            ...

        @staticmethod
        def _apply_active_catalog_predicate(query: Query[Any]) -> Query[Any]:
            ...

        @staticmethod
        def _money_to_cents(value: Any) -> int:
            ...

else:

    class ServiceAnalyticsRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
        model: type[ServiceAnalytics]
