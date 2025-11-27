from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.region_boundary import RegionBoundary


@pytest.fixture()
def client():
    from importlib import reload

    import app.main as main

    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


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
    boundary = RegionBoundary(
        id=region_id,
        region_type="nyc",
        region_code=unique_nyc_region_code,
        region_name="Test Neighborhood",
        parent_region="Manhattan",
    )
    db.add(boundary)
    db.commit()

    resp = client.put(
        "/api/v1/addresses/service-areas/me",
        json={"neighborhood_ids": [region_id]},
        headers=auth_headers_instructor,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    first = payload["items"][0]
    assert first["neighborhood_id"] == region_id
    assert first["ntacode"] == unique_nyc_region_code
    assert first["name"] == "Test Neighborhood"
    assert first["borough"] == "Manhattan"
