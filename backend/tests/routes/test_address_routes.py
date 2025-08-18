import os

import anyio
import pytest
from sqlalchemy import text

from app.auth import create_access_token
from app.core.config import settings
from app.repositories.region_boundary_repository import RegionBoundaryRepository
from app.repositories.user_repository import UserRepository
from app.services.geocoding.factory import create_geocoding_provider


def test_addresses_crud_flow(db, client):
    # Create a real user so FK constraints are satisfied
    # Create via repository pattern
    user_repo = UserRepository(db)
    user = user_repo.create(
        email="address.user@example.com",
        hashed_password="hashed",
        first_name="Addr",
        last_name="User",
        phone="+12125550000",
        zip_code="10001",
        is_active=True,
    )
    db.commit()

    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    # Empty list
    r = client.get("/api/addresses/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0

    # Create address (manual minimal)
    payload = {
        "street_line1": "123 Test St",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10001",
        "country_code": "US",
        "is_default": True,
    }
    r = client.post("/api/addresses/me", json=payload, headers=headers)
    assert r.status_code == 201
    a1 = r.json()
    assert a1["is_default"] is True

    # List now has one
    r = client.get("/api/addresses/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1

    # Update to set non-default
    r = client.patch(f"/api/addresses/me/{a1['id']}", json={"is_default": False}, headers=headers)
    assert r.status_code == 200
    a1u = r.json()
    assert a1u["is_default"] is False

    # Delete (soft)
    r = client.delete(f"/api/addresses/me/{a1['id']}", headers=headers)
    assert r.status_code == 200
    r = client.get("/api/addresses/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.skipif(os.getenv("RUN_LIVE_GEOCODING_TESTS", "false").lower() != "true", reason="Live geocoding disabled")
def test_address_create_with_google_place_id_verifies(db, client):
    # Skip if provider is not google or key missing
    if (settings.geocoding_provider or "google").lower() != "google":
        pytest.skip("GEOCODING_PROVIDER is not set to google")
    if not settings.google_maps_api_key:
        pytest.skip("GOOGLE_MAPS_API_KEY not configured")
    # Create user via repository
    user_repo = UserRepository(db)
    user = user_repo.create(
        email="geo.user@example.com",
        hashed_password="hashed",
        first_name="Geo",
        last_name="User",
        phone="+12125550001",
        zip_code="10001",
        is_active=True,
    )
    db.commit()

    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    # Known stable Google Place ID: Times Square (example)
    place_id = "ChIJmQJIxlVYwokRLgeuocVOGVU"

    payload = {
        "street_line1": "Times Square",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10036",
        "country_code": "US",
        "place_id": place_id,
        "is_default": True,
    }
    r = client.post("/api/addresses/me", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["verification_status"] == "verified"
    assert a["latitude"] is not None and a["longitude"] is not None


@pytest.mark.skipif(os.getenv("RUN_LIVE_GEOCODING_TESTS", "false").lower() != "true", reason="Live geocoding disabled")
def test_address_create_with_mapbox_feature_id_verifies(db, client):
    # Skip if provider is not mapbox or token missing
    if (settings.geocoding_provider or "").lower() != "mapbox":
        pytest.skip("GEOCODING_PROVIDER is not set to mapbox")
    if not settings.mapbox_access_token:
        pytest.skip("MAPBOX_ACCESS_TOKEN not configured")

    # Create user via repository
    user_repo = UserRepository(db)
    user = user_repo.create(
        email="geo.mapbox.user@example.com",
        hashed_password="hashed",
        first_name="Geo",
        last_name="MapboxUser",
        phone="+12125550002",
        zip_code="10001",
        is_active=True,
    )
    db.commit()

    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    # Use provider autocomplete to obtain a stable feature id
    provider = create_geocoding_provider()
    results = anyio.run(provider.autocomplete, "Times Square New York")
    assert results, "No Mapbox autocomplete results returned"
    feature_id = results[0].place_id

    payload = {
        "street_line1": "Times Square",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10036",
        "country_code": "US",
        "place_id": feature_id,
        "is_default": True,
    }
    r = client.post("/api/addresses/me", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["verification_status"] == "verified"
    assert a["latitude"] is not None and a["longitude"] is not None


def test_address_create_with_mock_provider_verifies_and_fallback(db, client, monkeypatch):
    # Force mock provider regardless of env
    monkeypatch.setenv("GEOCODING_PROVIDER", "mock")
    monkeypatch.setattr(settings, "geocoding_provider", "mock", raising=False)

    user_repo = UserRepository(db)
    user = user_repo.create(
        email="geo.mock.user@example.com",
        hashed_password="hashed",
        first_name="Geo",
        last_name="MockUser",
        phone="+12125550003",
        zip_code="10001",
        is_active=True,
    )
    db.commit()

    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    # 1) Happy path: mock details include coords → verified + coords present
    payload1 = {
        "street_line1": "1515 Broadway",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10036",
        "country_code": "US",
        "place_id": "mock:times_square",
        "is_default": True,
    }
    r1 = client.post("/api/addresses/me", json=payload1, headers=headers)
    assert r1.status_code == 201, r1.text
    a1 = r1.json()
    assert a1["verification_status"] == "verified"
    assert a1["latitude"] is not None and a1["longitude"] is not None

    # 2) Fallback path: mock place_details lacks coords (0.0), service should geocode() and fill them
    payload2 = {
        "street_line1": "1515 Broadway",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10036",
        "country_code": "US",
        "place_id": "mock:needs_fallback",
    }
    r2 = client.post("/api/addresses/me", json=payload2, headers=headers)
    assert r2.status_code == 201, r2.text
    a2 = r2.json()
    assert a2["verification_status"] == "verified"
    assert a2["latitude"] is not None and a2["longitude"] is not None


def test_places_autocomplete_with_mock_provider(db, client, monkeypatch):
    # Force mock provider
    monkeypatch.setenv("GEOCODING_PROVIDER", "mock")
    monkeypatch.setattr(settings, "geocoding_provider", "mock", raising=False)

    r = client.get("/api/addresses/places/autocomplete", params={"q": "Times"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any("place_id" in item and item["place_id"].startswith("mock:") for item in data["items"])


def test_enrichment_uses_region_boundaries(db, client, monkeypatch):
    # Seed a tiny polygon around Times Square and assert enrichment fills district/neighborhood
    # Create a square polygon around (40.7580, -73.9855)
    monkeypatch.setenv("GEOCODING_PROVIDER", "mock")
    monkeypatch.setattr(settings, "geocoding_provider", "mock", raising=False)

    # Ensure PostGIS is available; otherwise skip this test
    try:
        db.execute(text("SELECT postgis_full_version();"))
    except Exception:
        pytest.skip("PostGIS not available in test database")

    # Insert region boundary (WKT polygon); geometry columns exist in DB
    wkt_poly = "POLYGON((-73.9860 40.7575,-73.9850 40.7575,-73.9850 40.7585,-73.9860 40.7585,-73.9860 40.7575))"
    repo = RegionBoundaryRepository(db)
    # Clean up any leftover test regions via repository (repository pattern)
    repo.delete_by_region_name("Test Region A")
    repo.delete_by_region_code("TST", region_type="nyc")
    repo.insert_wkt(
        region_id="TESTREGION12345678901234",
        region_type="nyc",
        region_code="TSQ",
        region_name="Times Square Test",
        parent_region="Manhattan",
        wkt_polygon=wkt_poly,
        metadata={"community_district": 5},
    )
    db.commit()

    # Create a user and address inside the polygon using mock provider place with coords
    user_repo = UserRepository(db)
    user = user_repo.create(
        email="region.user@example.com",
        hashed_password="hashed",
        first_name="Region",
        last_name="User",
        phone="+12125550004",
        zip_code="10036",
        is_active=True,
    )
    db.commit()

    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    # Use mock place that returns Times Square coords
    payload = {
        "street_line1": "1515 Broadway",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10036",
        "country_code": "US",
        "place_id": "mock:times_square",
        "is_default": True,
    }
    r = client.post("/api/addresses/me", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["verification_status"] == "verified"
    # Enrichment populated
    assert a.get("district") == "Manhattan"
    assert a.get("neighborhood") == "Times Square Test"
    meta = a.get("location_metadata") or {}
    assert meta.get("region_type") == "nyc"
    assert (meta.get("nyc") or {}).get("community_district") == 5
