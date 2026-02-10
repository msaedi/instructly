"""Service layer for MCP service catalog tools."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.service_catalog import ServiceCatalog
from app.repositories.factory import RepositoryFactory
from app.services.base import BaseService


class MCPServiceCatalogService(BaseService):
    """Business logic for MCP service catalog endpoints."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.repository = RepositoryFactory.create_service_catalog_repository(db)

    @BaseService.measure_operation("mcp_services.catalog")
    def list_catalog_services(self) -> list[dict[str, object]]:
        services = self.repository.list_services_with_categories(include_inactive=True)
        return [self._service_to_dict(service) for service in services]

    @BaseService.measure_operation("mcp_services.lookup")
    def lookup_services(self, query: str, *, limit: int = 10) -> list[dict[str, object]]:
        query_clean = (query or "").strip()
        if not query_clean:
            return []
        services = self.repository.search_services_with_categories(
            query_clean,
            include_inactive=True,
            limit=limit,
        )
        return [self._service_to_dict(service) for service in services]

    @staticmethod
    def _service_to_dict(service: ServiceCatalog) -> dict[str, object]:
        subcategory = getattr(service, "subcategory", None)
        category = service.category  # @property traverses subcategory
        return {
            "id": service.id,
            "name": service.name,
            "slug": service.slug,
            "subcategory_name": getattr(subcategory, "name", None),
            "category_name": getattr(category, "name", None),
            "is_active": bool(getattr(service, "is_active", False)),
        }
