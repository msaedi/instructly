from __future__ import annotations

from datetime import datetime, timezone

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.repositories.service_catalog_repository import ServiceCatalogRepository


def _ensure_category(db, name: str) -> ServiceCategory:
    category = db.query(ServiceCategory).filter(ServiceCategory.name == name).first()
    if category:
        return category
    category = ServiceCategory(name=name)
    db.add(category)
    db.flush()
    return category


def _ensure_subcategory(db, category: ServiceCategory, name: str) -> ServiceSubcategory:
    subcategory = (
        db.query(ServiceSubcategory)
        .filter(ServiceSubcategory.category_id == category.id, ServiceSubcategory.name == name)
        .first()
    )
    if subcategory:
        return subcategory
    subcategory = ServiceSubcategory(name=name, category_id=category.id, display_order=1)
    db.add(subcategory)
    db.flush()
    return subcategory


def _create_service(db, *, name: str, slug: str, category_name: str, is_active: bool) -> ServiceCatalog:
    category = _ensure_category(db, category_name)
    subcategory = _ensure_subcategory(db, category, f"{category_name} General")
    service = ServiceCatalog(
        name=name,
        slug=slug,
        subcategory_id=subcategory.id,
        is_active=is_active,
    )
    service.created_at = datetime.now(timezone.utc)
    db.add(service)
    db.flush()
    return service


def test_service_catalog_repository_filters_and_searches(db):
    repo = ServiceCatalogRepository(db)
    active = _create_service(
        db,
        name="Swimming Lessons",
        slug="swim-lessons-test",
        category_name="Fitness MCP",
        is_active=True,
    )
    _create_service(
        db,
        name="Inactive Service",
        slug="inactive-service-test",
        category_name="Fitness MCP",
        is_active=False,
    )

    active_only = repo.list_services_with_categories(include_inactive=False)
    assert active.id in {svc.id for svc in active_only}

    repo._pg_trgm_available = False
    matches = repo.search_services_with_categories("swim", include_inactive=True, limit=5)
    assert active.id in {svc.id for svc in matches}

    paged = repo.get_active_services_with_categories(skip=1, limit=1)
    assert len(paged) <= 1
