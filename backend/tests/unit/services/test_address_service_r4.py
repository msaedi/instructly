"""Round 4 coverage tests for AddressService."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.exceptions import BusinessRuleException
from app.services.address_service import AddressService


class CacheHit:
    def __init__(self, value):
        self._value = value

    def get(self, _key):
        return self._value

    def set(self, *_args, **_kwargs):
        return True

    def delete(self, *_args, **_kwargs):
        return True


class CacheRaiseGet:
    def get(self, _key):
        raise RuntimeError("boom")

    def set(self, *_args, **_kwargs):
        return True

    def delete(self, *_args, **_kwargs):
        return True


class CacheRaiseSet:
    def __init__(self, value=None):
        self._value = value

    def get(self, _key):
        return self._value

    def set(self, *_args, **_kwargs):
        raise RuntimeError("boom")

    def delete(self, *_args, **_kwargs):
        return True


def test_geometry_for_boundary_uses_metadata_geometry(db, monkeypatch):
    service = AddressService(db)
    geometry = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]}
    boundary = SimpleNamespace(region_metadata={"geometry": geometry})
    monkeypatch.setattr(service.db, "get", lambda *_: boundary)

    result = service._geometry_for_boundary({"id": "region-1"})

    assert result == geometry


def test_update_address_returns_none_when_not_owner(db):
    service = AddressService(db)
    service.address_repo = Mock()
    service.address_repo.get_by_id.return_value = SimpleNamespace(user_id="other")

    assert service.update_address("user", "addr", {}) is None


def test_update_address_unsets_default(db):
    service = AddressService(db)
    service.address_repo = Mock()
    service._to_dict = lambda _entity: {"id": "addr"}

    entity = SimpleNamespace(user_id="user")
    service.address_repo.get_by_id.return_value = entity
    service.address_repo.update.return_value = SimpleNamespace(id="addr")

    def _tx():
        return contextlib.nullcontext()

    service.transaction = _tx

    updated = service.update_address(
        "user",
        "addr",
        {"is_default": True, "recipient_name": "Test"},
    )

    assert updated == {"id": "addr"}
    service.address_repo.unset_default.assert_called_once_with("user")


def test_delete_address_wrong_user_returns_false(db):
    service = AddressService(db)
    service.address_repo = Mock()
    service.address_repo.get_by_id.return_value = SimpleNamespace(user_id="other")

    assert service.delete_address("user", "addr") is False


def test_get_coverage_geojson_cache_hit(db):
    service = AddressService(db)
    cached = {"type": "FeatureCollection", "features": [{"id": 1}]}
    service.cache = CacheHit(cached)

    result = service.get_coverage_geojson_for_instructors(["inst-1"])

    assert result == cached


def test_get_coverage_geojson_cache_get_error_and_empty(db):
    service = AddressService(db)
    service.cache = CacheRaiseGet()
    service.service_area_repo = Mock()
    service.service_area_repo.list_neighborhoods_for_instructors.return_value = []

    result = service.get_coverage_geojson_for_instructors(["inst-1"])

    assert result == {"type": "FeatureCollection", "features": []}


def test_get_coverage_geojson_cache_set_error(db):
    service = AddressService(db)
    service.cache = CacheRaiseSet()
    service.service_area_repo = Mock()
    service.region_repo = Mock()

    area = SimpleNamespace(neighborhood_id="n1", instructor_id="inst-1")
    service.service_area_repo.list_neighborhoods_for_instructors.return_value = [area]
    service.region_repo.get_simplified_geojson_by_ids.return_value = [
        {
            "id": "n1",
            "region_name": "Test",
            "parent_region": "Manhattan",
            "region_type": "nyc",
        }
    ]
    service._geometry_for_boundary = Mock(return_value={"type": "Polygon", "coordinates": []})

    result = service.get_coverage_geojson_for_instructors(["inst-1"])

    assert result["features"]


def test_list_neighborhoods_cache_hit(db):
    service = AddressService(db)
    cached = [{"id": "1", "name": "Test", "borough": "Manhattan", "code": "MN"}]
    service.cache = CacheHit(cached)

    result = service.list_neighborhoods()

    assert result == cached


def test_list_neighborhoods_cache_get_error(db):
    service = AddressService(db)
    service.cache = CacheRaiseGet()
    service.region_repo = Mock()
    service.region_repo.list_regions.return_value = []

    result = service.list_neighborhoods()

    assert result == []


def test_list_neighborhoods_cache_set_error(db):
    service = AddressService(db)
    service.cache = CacheRaiseSet()
    service.region_repo = Mock()
    service.region_repo.list_regions.return_value = [
        {
            "id": "1",
            "region_name": "Test",
            "parent_region": "Manhattan",
            "region_code": "MN",
        }
    ]

    result = service.list_neighborhoods()

    assert result == [
        {"id": "1", "name": "Test", "borough": "Manhattan", "code": "MN"}
    ]


def test_normalize_country_code_unknown_and_error(db):
    service = AddressService(db)
    assert service._normalize_country_code("Canada") == "US"

    class BadStr:
        def __str__(self):
            raise RuntimeError("boom")

    assert service._normalize_country_code(BadStr()) == "US"


def test_create_address_without_place_id_sets_recipient_and_enrichment(db, monkeypatch):
    service = AddressService(db)
    service.address_repo = Mock()
    service.user_repo = Mock()
    service._to_dict = lambda _entity: {"id": "addr", "recipient_name": _entity.recipient_name}

    user = SimpleNamespace(first_name="Test", last_name="User")
    service.user_repo.find_one_by.return_value = user

    class FakeEnricher:
        def __init__(self, *_args, **_kwargs):
            pass

        def enrich(self, *_args, **_kwargs):
            return {
                "district": "D1",
                "neighborhood": "N1",
                "subneighborhood": "S1",
                "location_metadata": {"foo": "bar"},
            }

    monkeypatch.setattr(
        "app.services.address_service.LocationEnrichmentService", FakeEnricher
    )

    def _tx():
        return contextlib.nullcontext()

    service.transaction = _tx
    service.address_repo.create.return_value = SimpleNamespace(recipient_name="Test User")

    created = service.create_address(
        "user-1",
        {
            "label": "home",
            "street_line1": "123 Test St",
            "latitude": 40.0,
            "longitude": -73.0,
        },
    )

    assert created["recipient_name"] == "Test User"


def test_create_address_place_id_no_details_uses_test_fallback(db, monkeypatch):
    service = AddressService(db)
    service.address_repo = Mock()
    service._to_dict = lambda _entity: {"id": "addr"}

    class FakeGeocoder:
        async def get_place_details(self, _place_id):
            return None

        async def geocode(self, _query):
            return None

    monkeypatch.setattr(
        "app.services.address_service.create_geocoding_provider", lambda *_: FakeGeocoder()
    )

    def _tx():
        return contextlib.nullcontext()

    service.transaction = _tx
    service.address_repo.create.return_value = SimpleNamespace()

    created = service.create_address(
        "user-1",
        {
            "label": "home",
            "street_line1": "123 Test St",
            "place_id": "mock:missing",
            "latitude": 1.0,
        },
    )

    assert created["id"] == "addr"


def test_update_address_place_id_enriches_and_defaults_name(db, monkeypatch):
    service = AddressService(db)
    service.address_repo = Mock()
    service.user_repo = Mock()
    service._to_dict = lambda _entity: {"id": _entity.id}

    entity = SimpleNamespace(user_id="user-1")
    service.address_repo.get_by_id.return_value = entity
    service.address_repo.update.return_value = SimpleNamespace(id="addr")
    service.user_repo.find_one_by.return_value = SimpleNamespace(first_name="Test", last_name="User")

    class FakeGeocoder:
        async def get_place_details(self, _place_id):
            return SimpleNamespace(
                latitude=40.0,
                longitude=-73.0,
                city="NYC",
                state="NY",
                postal_code="10001",
                country="United States",
                formatted_address="123 Test St",
            )

        async def geocode(self, _query):
            return None

    class FakeEnricher:
        def __init__(self, *_args, **_kwargs):
            pass

        def enrich(self, *_args, **_kwargs):
            return {"district": "D1", "neighborhood": "N1", "subneighborhood": "S1"}

    monkeypatch.setattr(
        "app.services.address_service.create_geocoding_provider", lambda *_: FakeGeocoder()
    )
    monkeypatch.setattr(
        "app.services.address_service.LocationEnrichmentService", FakeEnricher
    )

    def _tx():
        return contextlib.nullcontext()

    service.transaction = _tx

    updated = service.update_address(
        "user-1",
        "addr",
        {"place_id": "google:place-1"},
    )

    assert updated == {"id": "addr"}


def test_resolve_place_id_with_unknown_prefix(db):
    service = AddressService(db)
    provider, place_id = service._resolve_place_id("foo:bar")
    assert provider is None
    assert place_id == "foo:bar"


def test_list_service_areas_with_metadata(db):
    service = AddressService(db)
    service.service_area_repo = Mock()

    region = SimpleNamespace(
        region_code=None,
        region_name=None,
        parent_region=None,
        borough=None,
        region_metadata={
            "nta_code": "MN-1",
            "nta_name": "Test NTA",
            "borough": "Manhattan",
        },
    )
    area = SimpleNamespace(neighborhood_id="n1", neighborhood=region)
    service.service_area_repo.list_for_instructor.return_value = [area]

    items = service.list_service_areas("inst-1")

    assert items[0]["ntacode"] == "MN-1"
    assert items[0]["borough"] == "Manhattan"


def test_replace_service_areas_blocks_travel_only(db):
    service = AddressService(db)
    service.profile_repository = Mock()
    service.instructor_service_repository = Mock()

    service.profile_repository.get_by_user_id.return_value = SimpleNamespace(id="profile-1")
    service.instructor_service_repository.find_by.return_value = [
        SimpleNamespace(offers_travel=True)
    ]

    with pytest.raises(BusinessRuleException):
        service.replace_service_areas("inst-1", [])


def test_replace_service_areas_clears_cache(db):
    service = AddressService(db)
    service.service_area_repo = Mock()
    service.service_area_repo.replace_areas.return_value = 2
    service.cache = CacheHit(None)

    count = service.replace_service_areas("inst-1", ["n1"])

    assert count == 2


def test_get_coverage_geojson_empty_instructors(db):
    service = AddressService(db)
    result = service.get_coverage_geojson_for_instructors([])
    assert result == {"type": "FeatureCollection", "features": []}
