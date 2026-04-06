"""Round 4 coverage tests for AddressService."""

from __future__ import annotations

import contextlib
from pathlib import Path
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


class CacheSpy:
    def __init__(self, value=None):
        self._value = value
        self.set_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def get(self, _key):
        return self._value

    def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return True

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


def test_get_neighborhood_polygons_cache_hit(db):
    service = AddressService(db)
    cached = {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
    service.cache = CacheHit(cached)

    result = service.get_neighborhood_polygons("nyc")

    assert result == cached


def test_get_neighborhood_polygons_cache_miss_stores_json(db):
    service = AddressService(db)
    service.cache = CacheSpy()
    service.region_repo = Mock()
    service.region_repo.get_all_active_polygons_geojson.return_value = [
        {
            "id": "n1",
            "region_name": "Upper East Side-Carnegie Hill",
            "parent_region": "Manhattan",
            "display_name": "Upper East Side",
            "display_key": "nyc-manhattan-upper-east-side",
            "geometry": {"type": "Polygon", "coordinates": []},
        }
    ]

    result = service.get_neighborhood_polygons("nyc")

    assert result["type"] == "FeatureCollection"
    assert result["features"] == [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": []},
            "properties": {
                "id": "n1",
                "display_key": "nyc-manhattan-upper-east-side",
                "display_name": "Upper East Side",
                "borough": "Manhattan",
                "region_name": "Upper East Side-Carnegie Hill",
            },
        }
    ]
    assert service.cache.set_calls == [
        (("neighborhood_polygons:nyc", '{"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {"id": "n1", "display_key": "nyc-manhattan-upper-east-side", "display_name": "Upper East Side", "borough": "Manhattan", "region_name": "Upper East Side-Carnegie Hill"}}]}'), {"ttl": 86400})
    ]


def test_get_neighborhood_polygons_rejects_unsupported_market(db):
    service = AddressService(db)

    with pytest.raises(BusinessRuleException):
        service.get_neighborhood_polygons("la")


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


def test_list_service_areas_with_display_metadata(db):
    service = AddressService(db)
    service.service_area_repo = Mock()

    region = SimpleNamespace(
        display_name="Test Neighborhood",
        display_key="nyc-manhattan-test-neighborhood",
        parent_region="Manhattan",
    )
    area = SimpleNamespace(neighborhood_id="n1", neighborhood=region)
    service.service_area_repo.list_for_instructor.return_value = [area]

    items = service.list_service_areas("inst-1")

    assert items[0]["display_name"] == "Test Neighborhood"
    assert items[0]["display_key"] == "nyc-manhattan-test-neighborhood"
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
    service.region_repo = Mock()
    service.region_repo.resolve_display_keys_to_ids.return_value = {
        "nyc-manhattan-test-neighborhood": ["n1", "n2"]
    }
    service.service_area_repo.replace_areas.return_value = 2
    service.cache = CacheHit(None)

    count = service.replace_service_areas("inst-1", ["nyc-manhattan-test-neighborhood"])

    assert count == 2


def test_replace_service_areas_empty_skips_display_key_resolution(db):
    service = AddressService(db)
    service.profile_repository = Mock()
    service.profile_repository.get_by_user_id.return_value = None
    service.instructor_service_repository = Mock()
    service.service_area_repo = Mock()
    service.service_area_repo.replace_areas.return_value = 0
    service.region_repo = Mock()

    count = service.replace_service_areas("inst-1", [])

    assert count == 0
    service.region_repo.resolve_display_keys_to_ids.assert_not_called()
    service.service_area_repo.replace_areas.assert_called_once_with("inst-1", [])


def test_get_neighborhood_selector_contract_aliases_and_cross_boroughs(db):
    service = AddressService(db)
    service.region_repo = Mock()
    service.region_repo.get_selector_items.return_value = [
        {
            "id": "q1",
            "region_name": "Baisley Park",
            "parent_region": "Queens",
            "display_name": "South Jamaica",
            "display_key": "nyc-queens-south-jamaica",
            "display_order": 1,
        },
        {
            "id": "q2",
            "region_name": "South Jamaica",
            "parent_region": "Queens",
            "display_name": "South Jamaica",
            "display_key": "nyc-queens-south-jamaica",
            "display_order": 1,
        },
        {
            "id": "b1",
            "region_name": "Bay Ridge",
            "parent_region": "Brooklyn",
            "display_name": "Bay Ridge",
            "display_key": "nyc-brooklyn-bay-ridge",
            "display_order": 1,
        },
        {
            "id": "b2",
            "region_name": "Fort Hamilton",
            "parent_region": "Brooklyn",
            "display_name": "Bay Ridge",
            "display_key": "nyc-brooklyn-bay-ridge",
            "display_order": 1,
        },
        {
            "id": "q3",
            "region_name": "Springfield Gardens (North)-Rochdale Village",
            "parent_region": "Queens",
            "display_name": "Springfield Gardens",
            "display_key": "nyc-queens-springfield-gardens",
            "display_order": 2,
        },
        {
            "id": "q4",
            "region_name": "Springfield Gardens (South)-Brookville",
            "parent_region": "Queens",
            "display_name": "Springfield Gardens",
            "display_key": "nyc-queens-springfield-gardens",
            "display_order": 2,
        },
        {
            "id": "q5",
            "region_name": "Jamaica Estates-Holliswood",
            "parent_region": "Queens",
            "display_name": "Jamaica Estates",
            "display_key": "nyc-queens-jamaica-estates",
            "display_order": 3,
        },
        {
            "id": "x1",
            "region_name": "Soundview-Bruckner-Bronx River",
            "parent_region": "Bronx",
            "display_name": "Soundview",
            "display_key": "nyc-bronx-soundview",
            "display_order": 1,
        },
        {
            "id": "x2",
            "region_name": "Soundview-Clason Point",
            "parent_region": "Bronx",
            "display_name": "Soundview",
            "display_key": "nyc-bronx-soundview",
            "display_order": 1,
        },
        {
            "id": "s1",
            "region_name": "Tompkinsville-Stapleton-Clifton-Fox Hills",
            "parent_region": "Staten Island",
            "display_name": "Tompkinsville / Stapleton / Clifton",
            "display_key": "nyc-staten-island-tompkinsville-stapleton-clifton",
            "display_order": 1,
        },
        {
            "id": "m1",
            "region_name": "Kingsbridge-Marble Hill",
            "parent_region": "Bronx",
            "display_name": "Kingsbridge / Marble Hill",
            "display_key": "nyc-bronx-kingsbridge-marble-hill",
            "display_order": 2,
        },
        {
            "id": "m2",
            "region_name": "Kingsbridge Heights-Van Cortlandt Village",
            "parent_region": "Bronx",
            "display_name": "Kingsbridge / Marble Hill",
            "display_key": "nyc-bronx-kingsbridge-marble-hill",
            "display_order": 2,
        },
    ]

    result = service.get_neighborhood_selector("nyc")
    items = {
        item["display_key"]: item
        for borough in result["boroughs"]
        for item in borough["items"]
    }

    south_jamaica_terms = {term["term"] for term in items["nyc-queens-south-jamaica"]["search_terms"]}
    assert "Baisley Park" in south_jamaica_terms

    bay_ridge_terms = {term["term"] for term in items["nyc-brooklyn-bay-ridge"]["search_terms"]}
    assert "Fort Hamilton" in bay_ridge_terms

    springfield_terms = {
        term["term"] for term in items["nyc-queens-springfield-gardens"]["search_terms"]
    }
    assert "Rochdale Village" in springfield_terms

    jamaica_estates_terms = {
        term["term"] for term in items["nyc-queens-jamaica-estates"]["search_terms"]
    }
    assert "Holliswood" in jamaica_estates_terms

    soundview_terms = {term["term"] for term in items["nyc-bronx-soundview"]["search_terms"]}
    assert "Clason Point" in soundview_terms

    stapleton_terms = {
        term["term"]
        for term in items["nyc-staten-island-tompkinsville-stapleton-clifton"]["search_terms"]
    }
    assert "Fox Hills" in stapleton_terms

    marble_hill_item = items["nyc-bronx-kingsbridge-marble-hill"]
    marble_hill_terms = {term["term"] for term in marble_hill_item["search_terms"]}
    assert "Marble Hill" in marble_hill_terms
    assert marble_hill_item["additional_boroughs"] == ["Manhattan"]

    assert all(item["display_name"] != "Central Park" for item in items.values())


def test_get_neighborhood_selector_rejects_unsupported_market(db):
    service = AddressService(db)

    with pytest.raises(BusinessRuleException, match="Unsupported market"):
        service.get_neighborhood_selector("la")


def test_get_neighborhood_selector_cache_hit_skips_repo(db):
    cached = {"market": "nyc", "boroughs": [], "total_items": 0}
    service = AddressService(db)
    service.cache = CacheHit(cached)
    service.region_repo = Mock()

    result = service.get_neighborhood_selector("nyc")

    assert result == cached
    service.region_repo.get_selector_items.assert_not_called()


def test_get_neighborhood_selector_cache_miss_stores_with_ttl(db):
    service = AddressService(db)
    service.region_repo = Mock()
    service.region_repo.get_selector_items.return_value = []
    service.cache = CacheSpy()

    result = service.get_neighborhood_selector("nyc")

    assert result == {"market": "nyc", "boroughs": [], "total_items": 0}
    assert service.cache.set_calls == [
        (("neighborhood_selector:nyc", result), {"ttl": 86400})
    ]


def test_get_neighborhood_selector_preserves_repository_order_without_resort(db):
    service = AddressService(db)
    service.region_repo = Mock()
    service.region_repo.get_selector_items.return_value = [
        {
            "id": "b2",
            "region_name": "Zulu",
            "parent_region": "Manhattan",
            "display_name": "Beta",
            "display_key": "beta",
            "display_order": 2,
        },
        {
            "id": "b1",
            "region_name": "Alpha",
            "parent_region": "Manhattan",
            "display_name": "Beta",
            "display_key": "beta",
            "display_order": 2,
        },
        {
            "id": "a2",
            "region_name": "Zulu",
            "parent_region": "Manhattan",
            "display_name": "Alpha",
            "display_key": "alpha",
            "display_order": 1,
        },
    ]

    result = service.get_neighborhood_selector("nyc")

    borough_items = result["boroughs"][0]["items"]
    assert [item["display_key"] for item in borough_items] == ["beta", "alpha"]
    assert borough_items[0]["nta_ids"] == ["b2", "b1"]


def test_replace_service_areas_rejects_invalid_display_key(db):
    service = AddressService(db)
    service.region_repo = Mock()
    service.region_repo.resolve_display_keys_to_ids.return_value = {}

    with pytest.raises(BusinessRuleException):
        service.replace_service_areas("inst-1", ["nyc-manhattan-central-park"])


def test_public_api_has_no_neighborhood_ids_references():
    backend_root = Path(__file__).resolve().parents[3]
    schema_and_route_files = [
        *sorted((backend_root / "app" / "schemas").rglob("*.py")),
        *sorted((backend_root / "app" / "routes").rglob("*.py")),
    ]
    assert schema_and_route_files
    matches = [
        str(path)
        for path in schema_and_route_files
        if "neighborhood_ids" in path.read_text(encoding="utf-8")
    ]
    assert matches == []


def test_get_coverage_geojson_empty_instructors(db):
    service = AddressService(db)
    result = service.get_coverage_geojson_for_instructors([])
    assert result == {"type": "FeatureCollection", "features": []}
