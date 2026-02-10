from __future__ import annotations

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.services.mcp_service_catalog_service import MCPServiceCatalogService


def _ensure_category(db, name: str) -> ServiceCategory:
    category = db.query(ServiceCategory).filter(ServiceCategory.name == name).first()
    if category:
        return category
    category = ServiceCategory(name=name)
    db.add(category)
    db.flush()
    return category


def _ensure_subcategory(db, category_id: str) -> ServiceSubcategory:
    subcategory = db.query(ServiceSubcategory).filter(ServiceSubcategory.category_id == category_id).first()
    if subcategory:
        return subcategory
    subcategory = ServiceSubcategory(name="General", category_id=category_id, display_order=1)
    db.add(subcategory)
    db.flush()
    return subcategory


def test_mcp_service_catalog_service_empty_lookup(db):
    service = MCPServiceCatalogService(db)
    assert service.lookup_services("   ") == []


def test_mcp_service_catalog_service_lists_inactive(db):
    category = _ensure_category(db, "Mcp Services")
    subcategory = _ensure_subcategory(db, category.id)
    inactive = ServiceCatalog(
        name="Inactive Catalog Service",
        slug="inactive-catalog-service",
        subcategory_id=subcategory.id,
        is_active=False,
    )
    db.add(inactive)
    db.flush()

    service = MCPServiceCatalogService(db)
    items = service.list_catalog_services()
    slugs = {item["slug"] for item in items}
    assert "inactive-catalog-service" in slugs
