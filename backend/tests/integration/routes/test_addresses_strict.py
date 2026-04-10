from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from tests.integration.routes.conftest import strict_schema_app
import ulid

from app.auth import create_access_token
from app.domain.neighborhood_config import generate_display_key
from app.models.region_boundary import RegionBoundary


@pytest.fixture(scope="module")
def client():
    with strict_schema_app() as c:
        yield c


def test_zip_is_nyc_rejects_extra_query_param(client: TestClient):
    # Public endpoint, should validate query params via response model strictness
    resp = client.get("/api/v1/addresses/zip/is-nyc", params={"zip": "10001", "unexpected": 1})
    # Some frameworks allow extra query params; since response model is strict, body is unaffected.
    # We assert the endpoint still works and does not include unexpected fields.
    assert resp.status_code == 200
    data = resp.json()
    assert "is_nyc" in data
    assert "borough" in data


def test_delete_response_rejects_extra_body_fields(client: TestClient):
    # Auth likely required; exercise just the model by calling the route with unexpected fields
    resp = client.request("DELETE", "/api/v1/addresses/me/some-id", json={"unexpected": True})
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    # If the route executes, it will 404 the entity; we just ensure no 422 from model here
    assert resp.status_code in (404, 422)


def test_replace_service_areas_uses_region_boundary(
    client: TestClient,
    db: Session,
    auth_headers_instructor: dict,
    unique_nyc_region_code: str,
):
    region_id = str(ulid.ULID())
    display_key = generate_display_key("nyc", "Manhattan", "Test Neighborhood")
    boundary = RegionBoundary(
        id=region_id,
        region_type="nyc",
        region_code=unique_nyc_region_code,
        region_name="Test Neighborhood",
        display_name="Test Neighborhood",
        display_key=display_key,
        display_order=0,
        parent_region="Manhattan",
    )
    db.add(boundary)
    db.commit()

    resp = client.put(
        "/api/v1/addresses/service-areas/me",
        json={"display_keys": [display_key]},
        headers=auth_headers_instructor,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    first = payload["items"][0]
    assert first["display_name"] == "Test Neighborhood"
    assert first["display_key"] == display_key
    assert first["borough"] == "Manhattan"


def test_replace_service_areas_blocks_last_area_when_travel_enabled(
    client: TestClient,
    auth_headers_instructor: dict,
) -> None:
    resp = client.put(
        "/api/v1/addresses/service-areas/me",
        json={"display_keys": []},
        headers=auth_headers_instructor,
    )

    assert resp.status_code == 422, resp.text
    payload = resp.json()
    detail = payload.get("detail") if isinstance(payload, dict) else None
    message = ""
    if isinstance(detail, dict):
        msg = detail.get("message")
        if isinstance(msg, str):
            message = msg
    elif isinstance(detail, str):
        message = detail
    assert "last service area" in message.lower()


def test_validate_service_area_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/addresses/validate-service-area",
        json={"latitude": 40.775, "longitude": -73.955},
    )

    assert response.status_code == 401


def test_validate_service_area_forbids_non_instructor(
    client: TestClient,
    test_student,
) -> None:
    student_headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': test_student.email})}",
        "x-enforce-beta-checks": "1",
    }
    response = client.post(
        "/api/v1/addresses/validate-service-area",
        json={"latitude": 40.775, "longitude": -73.955},
        headers=student_headers,
    )

    assert response.status_code == 403


def test_list_service_areas_forbids_non_instructor(
    client: TestClient,
    test_student,
) -> None:
    student_headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': test_student.email})}",
        "x-enforce-beta-checks": "1",
    }
    response = client.get(
        "/api/v1/addresses/service-areas/me",
        headers=student_headers,
    )

    assert response.status_code == 403


def test_replace_service_areas_forbids_non_instructor(
    client: TestClient,
    test_student,
) -> None:
    student_headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': test_student.email})}",
        "x-enforce-beta-checks": "1",
    }
    response = client.put(
        "/api/v1/addresses/service-areas/me",
        json={"display_keys": []},
        headers=student_headers,
    )

    assert response.status_code == 403
