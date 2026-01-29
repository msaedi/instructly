from __future__ import annotations

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.services.mcp_service_catalog_service import MCPServiceCatalogService


def _ensure_category(db, slug: str) -> ServiceCategory:
    category = db.query(ServiceCategory).filter(ServiceCategory.slug == slug).first()
    if category:
        return category
    category = ServiceCategory(name=slug.title(), slug=slug)
    db.add(category)
    db.flush()
    return category


def test_mcp_service_catalog_service_empty_lookup(db):
    service = MCPServiceCatalogService(db)
    assert service.lookup_services("   ") == []


def test_mcp_service_catalog_service_lists_inactive(db):
    category = _ensure_category(db, "mcp-services")
    inactive = ServiceCatalog(
        name="Inactive Catalog Service",
        slug="inactive-catalog-service",
        category_id=category.id,
        is_active=False,
    )
    db.add(inactive)
    db.flush()

    service = MCPServiceCatalogService(db)
    items = service.list_catalog_services()
    slugs = {item["slug"] for item in items}
    assert "inactive-catalog-service" in slugs
