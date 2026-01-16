import types

from fastapi import HTTPException
import pytest

from app.routes.v1 import addresses as addresses_routes
from app.services.geocoding.base import AutocompleteResult, GeocodedAddress


def _make_geocoded_address(provider_id: str) -> GeocodedAddress:
    return GeocodedAddress(
        latitude=40.7,
        longitude=-73.9,
        formatted_address="123 Test St, New York, NY",
        street_number="123",
        street_name="Test St",
        city="New York",
        state="NY",
        postal_code="10001",
        country="US",
        provider_id=provider_id,
        provider_data={"raw": True},
        confidence_score=0.9,
    )


def test_nyc_zip_to_borough_and_invalid():
    assert addresses_routes._nyc_zip_to_borough("10001") == "Manhattan"
    assert addresses_routes._nyc_zip_to_borough("10301") == "Staten Island"
    assert addresses_routes._nyc_zip_to_borough("10451") == "Bronx"
    assert addresses_routes._nyc_zip_to_borough("11201") == "Brooklyn"
    assert addresses_routes._nyc_zip_to_borough("11101") == "Queens"
    assert addresses_routes._nyc_zip_to_borough("11004") == "Queens"
    assert addresses_routes._nyc_zip_to_borough("11351") == "Queens"
    assert addresses_routes._nyc_zip_to_borough("11411") == "Queens"
    assert addresses_routes._nyc_zip_to_borough("11691") == "Queens"
    assert addresses_routes._nyc_zip_to_borough("ABCDE") is None

    response = addresses_routes.is_nyc_zip("12")
    assert response.is_nyc is False
    assert response.borough is None

    response_valid = addresses_routes.is_nyc_zip("10001")
    assert response_valid.is_nyc is True
    assert response_valid.borough == "Manhattan"


def test_get_address_service_instantiates(monkeypatch):
    class DummyService:
        def __init__(self, db):
            self.db = db

    dummy_db = object()
    monkeypatch.setattr(addresses_routes, "AddressService", DummyService)

    service = addresses_routes.get_address_service(db=dummy_db)
    assert isinstance(service, DummyService)
    assert service.db is dummy_db


def test_list_my_addresses_builds_response(test_student):
    class StubService:
        def list_addresses(self, _user_id):
            return [
                {
                    "id": "addr1",
                    "is_active": True,
                    "street_line1": "123 Test St",
                    "locality": "New York",
                    "administrative_area": "NY",
                    "postal_code": "10001",
                    "country_code": "US",
                    "is_default": True,
                }
            ]

    response = addresses_routes.list_my_addresses(
        current_user=test_student,
        service=StubService(),
    )
    assert response.total == 1
    assert response.items[0].id == "addr1"


@pytest.mark.asyncio
async def test_invalidate_user_address_cache_handles_error():
    class StubCache:
        async def delete(self, _key):
            raise RuntimeError("cache down")

    await addresses_routes._invalidate_user_address_cache(StubCache(), "user_1")


def test_update_and_delete_address_not_found(test_student):
    class StubService:
        def update_address(self, *_args, **_kwargs):
            return None

        def delete_address(self, *_args, **_kwargs):
            return False

    service = StubService()
    update_payload = addresses_routes.AddressUpdate(is_default=False)

    with pytest.raises(HTTPException) as excinfo:
        addresses_routes.update_my_address(
            address_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            data=update_payload,
            current_user=test_student,
            service=service,
            cache_service=types.SimpleNamespace(),
        )
    assert excinfo.value.status_code == 404

    with pytest.raises(HTTPException) as excinfo:
        addresses_routes.delete_my_address(
            address_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            current_user=test_student,
            service=service,
            cache_service=types.SimpleNamespace(),
        )
    assert excinfo.value.status_code == 404


def test_list_service_areas_and_neighborhoods_clamp(test_instructor):
    class StubService:
        def __init__(self):
            self.neighborhood_args = None

        def list_service_areas(self, _user_id):
            return [{"neighborhood_id": "area1", "name": "Chelsea", "borough": "Manhattan"}]

        def list_neighborhoods(self, region_type, borough, limit, offset):
            self.neighborhood_args = (region_type, borough, limit, offset)
            return [{"id": "n1", "name": "Chelsea", "borough": "Manhattan"}]

    service = StubService()

    service_areas = addresses_routes.list_my_service_areas(
        current_user=test_instructor,
        service=service,
    )
    assert service_areas.total == 1
    assert service_areas.items[0].name == "Chelsea"

    neighborhoods = addresses_routes.list_neighborhoods(
        region_type="nyc",
        borough="Manhattan",
        page=0,
        per_page=600,
        service=service,
    )
    assert neighborhoods.page == 1
    assert neighborhoods.per_page == 500
    assert service.neighborhood_args == ("nyc", "Manhattan", 500, 0)


def test_places_autocomplete_scopes(monkeypatch):
    calls = []

    class StubGeocoder:
        async def autocomplete(self, query, session_token=None, *, country=None, location_bias=None):
            calls.append((query, country, location_bias))
            return [
                AutocompleteResult(
                    text="Times Square",
                    place_id="place_1",
                    description="Times Square",
                    types=["place"],
                )
            ]

    def stub_factory(_provider):
        return StubGeocoder()

    monkeypatch.setattr(
        "app.services.geocoding.factory.create_geocoding_provider",
        stub_factory,
    )

    addresses_routes.places_autocomplete(q="Times", provider="google", scope="global")
    addresses_routes.places_autocomplete(q="Times", provider="google", scope="us")
    addresses_routes.places_autocomplete(q="Times", provider="google")

    assert calls[0][1] is None
    assert calls[0][2] is None
    assert calls[1][1] == "US"
    assert calls[1][2] is None
    assert calls[2][1] == "US"
    assert calls[2][2] == addresses_routes.NYC_AUTOCOMPLETE_BIAS


def test_place_details_provider_mismatch_raises_422(monkeypatch):
    class StubGeocoder:
        async def get_place_details(self, _place_id):
            return None

    def stub_factory(_provider):
        return StubGeocoder()

    monkeypatch.setattr(
        "app.services.geocoding.factory.create_geocoding_provider",
        stub_factory,
    )

    with pytest.raises(HTTPException) as excinfo:
        addresses_routes.place_details(place_id="place_123", provider="google")
    assert excinfo.value.status_code == 422


def test_place_details_fallback_to_mapbox_with_prefix(monkeypatch):
    class GoogleGeocoder:
        async def get_place_details(self, _place_id):
            return None

    class MapboxGeocoder:
        async def get_place_details(self, _place_id):
            return _make_geocoded_address("mb_123")

    def stub_factory(provider):
        if provider == "google":
            return GoogleGeocoder()
        if provider == "mapbox":
            return MapboxGeocoder()
        raise ValueError("Unexpected provider")

    monkeypatch.setattr(
        "app.services.geocoding.factory.create_geocoding_provider",
        stub_factory,
    )

    result = addresses_routes.place_details(place_id="google:place_123")
    assert result.provider_id == "mapbox:mb_123"


def test_place_details_fallback_returns_none_404(monkeypatch):
    class StubGeocoder:
        async def get_place_details(self, _place_id):
            return None

    def stub_factory(provider):
        if provider in {"google", "mapbox"}:
            return StubGeocoder()
        raise RuntimeError("No provider")

    monkeypatch.setattr(
        "app.services.geocoding.factory.create_geocoding_provider",
        stub_factory,
    )

    with pytest.raises(HTTPException) as excinfo:
        addresses_routes.place_details(place_id="place_123", provider=None)
    assert excinfo.value.status_code == 404


def test_place_details_prefix_unrecognized_uses_default_provider(monkeypatch):
    class StubGeocoder:
        async def get_place_details(self, _place_id):
            return _make_geocoded_address("google:abc")

    def stub_factory(_provider):
        return StubGeocoder()

    monkeypatch.setattr(
        "app.services.geocoding.factory.create_geocoding_provider",
        stub_factory,
    )
    monkeypatch.setattr("app.core.config.settings.geocoding_provider", "google", raising=False)

    result = addresses_routes.place_details(place_id="foo:bar", provider=None)
    assert result.provider_id == "google:abc"


def test_bulk_coverage_geojson_limit_and_empty(test_student):
    class StubService:
        def __init__(self):
            self.coverage_ids = None

        def get_coverage_geojson_for_instructors(self, instructor_ids):
            self.coverage_ids = instructor_ids
            return {"type": "FeatureCollection", "features": []}

    service = StubService()

    empty_result = addresses_routes.get_bulk_coverage_geojson.__wrapped__(
        ids="",
        service=service,
    )
    assert empty_result.features == []

    ids = ",".join([f"id_{i}" for i in range(101)])
    addresses_routes.get_bulk_coverage_geojson.__wrapped__(
        ids=ids,
        service=service,
    )
    assert len(service.coverage_ids) == 100

    addresses_routes.get_bulk_coverage_geojson.__wrapped__(
        ids="id_1,id_2",
        service=service,
    )
    assert service.coverage_ids == ["id_1", "id_2"]


def test_replace_my_service_areas(test_instructor):
    class StubService:
        def __init__(self):
            self.replaced = None

        def replace_service_areas(self, _user_id, neighborhood_ids):
            self.replaced = neighborhood_ids

        def list_service_areas(self, _user_id):
            return [{"neighborhood_id": "area1", "name": "Chelsea"}]

    service = StubService()

    response = addresses_routes.replace_my_service_areas(
        payload=addresses_routes.ServiceAreasUpdateRequest(neighborhood_ids=["area1"]),
        current_user=test_instructor,
        service=service,
    )
    assert service.replaced == ["area1"]
    assert response.total == 1
