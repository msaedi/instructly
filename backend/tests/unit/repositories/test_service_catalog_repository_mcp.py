from __future__ import annotations

from datetime import datetime, timezone

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.repositories.service_catalog_repository import ServiceCatalogRepository


def _ensure_category(db, slug: str) -> ServiceCategory:
    category = db.query(ServiceCategory).filter(ServiceCategory.slug == slug).first()
    if category:
        return category
    category = ServiceCategory(name=slug.title(), slug=slug)
    db.add(category)
    db.flush()
    return category


def _create_service(db, *, name: str, slug: str, category_slug: str, is_active: bool) -> ServiceCatalog:
    category = _ensure_category(db, category_slug)
    service = ServiceCatalog(
        name=name,
        slug=slug,
        category_id=category.id,
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
        category_slug="fitness-mcp",
        is_active=True,
    )
    _create_service(
        db,
        name="Inactive Service",
        slug="inactive-service-test",
        category_slug="fitness-mcp",
        is_active=False,
    )

    active_only = repo.list_services_with_categories(include_inactive=False)
    assert active.id in {svc.id for svc in active_only}

    repo._pg_trgm_available = False
    matches = repo.search_services_with_categories("swim", include_inactive=True, limit=5)
    assert active.id in {svc.id for svc in matches}

    paged = repo.get_active_services_with_categories(skip=1, limit=1)
    assert len(paged) <= 1
