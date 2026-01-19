from __future__ import annotations

from types import SimpleNamespace

from app.models.region_boundary import RegionBoundary
from app.services.address_service import AddressService
from app.services.cache_service import CacheServiceSyncAdapter


class FakeGeocoder:
    def __init__(self, details=None, geocode_result=None) -> None:
        self._details = details
        self._geocode = geocode_result

    async def get_place_details(self, _place_id: str):
        return self._details

    async def geocode(self, _query: str):
        return self._geocode


class FakeCacheService:
    def __init__(self) -> None:
        self.key_builder = SimpleNamespace()
        self.store = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, ttl=None, tier: str = "warm"):
        self.store[key] = value
        return True

    async def delete(self, key: str):
        self.store.pop(key, None)
        return True


def test_address_create_update_and_delete(db, test_student, monkeypatch):
    details = SimpleNamespace(
        latitude=None,
        longitude=None,
        city="New York",
        state="NY",
        postal_code="10001",
        country="United States",
        formatted_address="123 Test St, New York, NY",
    )
    fallback = SimpleNamespace(
        latitude=40.75,
        longitude=-73.99,
        city="New York",
        state="NY",
        postal_code="10001",
        country="US",
        formatted_address="123 Test St, New York, NY",
    )

    geocoder = FakeGeocoder(details=details, geocode_result=fallback)
    monkeypatch.setattr(
        "app.services.address_service.create_geocoding_provider",
        lambda *_: geocoder,
    )

    service = AddressService(db)
    created = service.create_address(
        test_student.id,
        {
            "label": "home",
            "street_line1": "123 Test St",
            "place_id": "mock:place-1",
            "is_default": True,
        },
    )
    assert created["verification_status"] == "verified"
    assert created["latitude"] is not None
    assert created["longitude"] is not None

    updated = service.update_address(
        test_student.id,
        created["id"],
        {"place_id": "google:place-2", "custom_label": "Updated"},
    )
    assert updated is not None
    assert updated["custom_label"] == "Updated"

    assert service.list_addresses(test_student.id)
    assert service.delete_address(test_student.id, created["id"]) is True


def test_address_geocode_fallback_when_details_missing(db, test_student, monkeypatch):
    fallback = SimpleNamespace(
        latitude=40.7,
        longitude=-74.0,
        city="New York",
        state="NY",
        postal_code="10002",
        country="US",
        formatted_address="456 Broadway, New York, NY",
    )
    geocoder = FakeGeocoder(details=None, geocode_result=fallback)
    monkeypatch.setattr(
        "app.services.address_service.create_geocoding_provider",
        lambda *_: geocoder,
    )

    service = AddressService(db)
    created = service.create_address(
        test_student.id,
        {
            "label": "work",
            "street_line1": "456 Broadway",
            "place_id": "mapbox:place-3",
        },
    )
    assert created["verification_status"] == "verified"
    assert created["latitude"] is not None
    assert created["country_code"] == "US"


def test_service_areas_geojson_and_neighborhoods(db, test_instructor):
    service = AddressService(db, cache_service=CacheServiceSyncAdapter(FakeCacheService()))

    areas = service.list_service_areas(test_instructor.id)
    assert areas

    neighborhood_ids = [area["neighborhood_id"] for area in areas if area.get("neighborhood_id")]
    assert neighborhood_ids

    assert service.replace_service_areas(test_instructor.id, neighborhood_ids) >= 1

    coverage = service.get_coverage_geojson_for_instructors([test_instructor.id])
    assert coverage["type"] == "FeatureCollection"
    assert coverage["features"]

    regions = db.query(RegionBoundary).order_by(RegionBoundary.region_name).limit(5).all()
    assert regions
    borough = regions[0].parent_region
    neighborhoods = service.list_neighborhoods(borough=borough, limit=10, offset=0)
    assert neighborhoods


def test_geometry_fallbacks(db):
    service = AddressService(db, cache_service=CacheServiceSyncAdapter(FakeCacheService()))
    geom = {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
    }
    assert service._geometry_for_boundary({"geometry": geom}) == geom

    boundary = RegionBoundary(
        region_type="nyc",
        region_name="Test Region",
        parent_region="Manhattan",
        region_metadata={"centroid": [-73.9, 40.7]},
    )
    db.add(boundary)
    db.commit()

    fallback = service._geometry_for_boundary({"id": boundary.id})
    assert fallback["type"] == "Polygon"
    assert fallback["coordinates"]


def test_create_address_test_mode_fallback_and_update(db, test_student, monkeypatch):
    geocoder = FakeGeocoder(details=None, geocode_result=None)
    monkeypatch.setattr(
        "app.services.address_service.create_geocoding_provider",
        lambda *_: geocoder,
    )

    service = AddressService(db, cache_service=CacheServiceSyncAdapter(FakeCacheService()))
    created = service.create_address(
        test_student.id,
        {
            "label": "home",
            "street_line1": "No Geo",
            "locality": "New York",
            "administrative_area": "NY",
            "postal_code": "10001",
            "country_code": "US",
            "place_id": "mock:missing",
        },
    )
    assert created["verification_status"] == "verified"
    assert created["latitude"] is not None
    assert created["recipient_name"]

    updated = service.update_address(
        test_student.id,
        created["id"],
        {"place_id": "mock:missing-update"},
    )
    assert updated is not None
    assert updated["verification_status"] == "verified"


def test_address_helper_utilities(db):
    service = AddressService(db, cache_service=CacheServiceSyncAdapter(FakeCacheService()))
    assert service._normalize_country_code(None) == "US"
    assert service._normalize_country_code("us") == "US"
    assert service._normalize_country_code("United States of America") == "US"

    provider, place_id = service._resolve_place_id("google:place-1")
    assert provider == "google"
    assert place_id == "place-1"

    provider, place_id = service._resolve_place_id("unknown-place")
    assert provider is None
    assert place_id == "unknown-place"


def test_address_service_cache_init_fallback(db, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("cache fail")

    monkeypatch.setattr("app.services.address_service.get_cache_service", _raise)
    service = AddressService(db)
    assert service.cache is None


def test_geometry_fallback_db_error(db, monkeypatch):
    service = AddressService(db, cache_service=CacheServiceSyncAdapter(FakeCacheService()))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db error")

    monkeypatch.setattr(service.db, "get", _boom)
    geom = service._geometry_for_boundary({"id": "missing", "parent_region": "Queens"})
    assert geom["type"] == "Polygon"
