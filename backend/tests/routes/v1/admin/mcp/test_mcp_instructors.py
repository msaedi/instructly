from fastapi.testclient import TestClient

from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory


def _ensure_service(db, slug: str) -> ServiceCatalog:
    service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == slug).first()
    if service:
        return service
    category = db.query(ServiceCategory).first()
    if not category:
        category = ServiceCategory(name="Test Category")
        db.add(category)
        db.flush()
    subcategory = db.query(ServiceSubcategory).filter(ServiceSubcategory.category_id == category.id).first()
    if not subcategory:
        subcategory = ServiceSubcategory(name="General", category_id=category.id, display_order=1)
        db.add(subcategory)
        db.flush()
    service = ServiceCatalog(name=slug.title(), slug=slug, subcategory_id=subcategory.id)
    db.add(service)
    db.flush()
    return service


def test_list_instructors_structure(client: TestClient, mcp_service_headers):
    res = client.get("/api/v1/admin/mcp/instructors", headers=mcp_service_headers)
    assert res.status_code == 200
    data = res.json()
    assert "meta" in data
    assert "items" in data
    assert "limit" in data


def test_list_instructors_filters(
    client: TestClient, db, test_instructor, test_instructor_2, mcp_service_headers
):
    profile_2 = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor_2.id)
        .first()
    )
    assert profile_2 is not None
    profile_2.is_live = False
    profile_2.onboarding_completed_at = None
    profile_2.skills_configured = False
    profile_2.bgc_status = None
    db.flush()

    res = client.get(
        "/api/v1/admin/mcp/instructors",
        headers=mcp_service_headers,
        params={"status": "registered"},
    )
    assert res.status_code == 200
    data = res.json()
    ids = {item["user_id"] for item in data["items"]}
    assert test_instructor_2.id in ids

    res = client.get(
        "/api/v1/admin/mcp/instructors",
        headers=mcp_service_headers,
        params={"service_slug": "piano"},
    )
    assert res.status_code == 200
    data = res.json()
    assert any(item["user_id"] == test_instructor.id for item in data["items"])

    res = client.get(
        "/api/v1/admin/mcp/instructors",
        headers=mcp_service_headers,
        params={"is_founding": True},
    )
    assert res.status_code == 200


def test_service_coverage_endpoint(client: TestClient, db, test_instructor_2, mcp_service_headers):
    profile_2 = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor_2.id)
        .first()
    )
    assert profile_2 is not None
    yoga = _ensure_service(db, "yoga")
    db.add(
        Service(
            instructor_profile_id=profile_2.id,
            service_catalog_id=yoga.id,
            hourly_rate=60.0,
            is_active=True,
        )
    )
    db.flush()

    res = client.get(
        "/api/v1/admin/mcp/instructors/coverage",
        headers=mcp_service_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "meta" in data
    assert "data" in data
    assert data["data"]["group_by"] == "category"

    res = client.get(
        "/api/v1/admin/mcp/instructors/coverage",
        headers=mcp_service_headers,
        params={"group_by": "service"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["data"]["group_by"] == "service"


def test_instructor_detail_lookup(client: TestClient, db, test_instructor, mcp_service_headers):
    user_id = test_instructor.id
    res = client.get(f"/api/v1/admin/mcp/instructors/{user_id}", headers=mcp_service_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == user_id

    res = client.get(
        f"/api/v1/admin/mcp/instructors/{test_instructor.email}",
        headers=mcp_service_headers,
    )
    assert res.status_code == 200

    test_instructor.first_name = f"Unique{test_instructor.id[-4:]}"
    test_instructor.last_name = f"Name{test_instructor.id[-6:]}"
    db.flush()
    full_name = f"{test_instructor.first_name} {test_instructor.last_name}"
    res = client.get(
        f"/api/v1/admin/mcp/instructors/{full_name}",
        headers=mcp_service_headers,
    )
    assert res.status_code == 200


def test_instructor_detail_not_found(client: TestClient, mcp_service_headers):
    res = client.get(
        "/api/v1/admin/mcp/instructors/Unknown%20Person",
        headers=mcp_service_headers,
    )
    assert res.status_code == 404


def test_instructors_reject_invalid_token(client: TestClient, mcp_service_headers):
    res = client.get(
        "/api/v1/admin/mcp/instructors",
        headers={"Authorization": "Bearer invalid"},
    )
    assert res.status_code == 401
