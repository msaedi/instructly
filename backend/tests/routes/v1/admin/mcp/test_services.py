from fastapi.testclient import TestClient

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory


def _ensure_category(db, name: str = "Fitness") -> ServiceCategory:
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


def _create_service(db, name: str, slug: str, category_name: str = "Fitness") -> ServiceCatalog:
    service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == slug).first()
    if service:
        return service
    category = _ensure_category(db, category_name)
    subcategory = _ensure_subcategory(db, category, f"{category_name} General")
    service = ServiceCatalog(name=name, slug=slug, subcategory_id=subcategory.id, is_active=True)
    db.add(service)
    db.flush()
    return service


def test_services_catalog_lists_items(client: TestClient, db, mcp_service_headers):
    service = _create_service(db, "Swimming Lessons", "swimming")

    res = client.get("/api/v1/admin/mcp/services/catalog", headers=mcp_service_headers)
    assert res.status_code == 200
    payload = res.json()
    assert "meta" in payload
    assert "data" in payload
    slugs = {item["slug"] for item in payload["data"]["services"]}
    assert service.slug in slugs


def test_services_lookup_matches_slug(client: TestClient, db, mcp_service_headers):
    _create_service(db, "Swimming Lessons", "swimming")

    res = client.get(
        "/api/v1/admin/mcp/services/lookup",
        headers=mcp_service_headers,
        params={"q": "swim"},
    )
    assert res.status_code == 200
    payload = res.json()
    slugs = {item["slug"] for item in payload["data"]["matches"]}
    assert "swimming" in slugs


def test_services_lookup_no_match_returns_message(client: TestClient, mcp_service_headers):
    res = client.get(
        "/api/v1/admin/mcp/services/lookup",
        headers=mcp_service_headers,
        params={"q": "xyz123"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["data"]["count"] == 0
    assert payload["data"]["message"]
